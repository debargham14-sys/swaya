"""
Markerless body-measurement estimator (no DSV vest).

Inputs: front photo + side photo + height(cm) + weight(kg).
Method (slice-sweep):
  1. segment the body in each view (MediaPipe / GrabCut)
  2. height -> scale (cm per pixel) from silhouette stature
  3. sweep horizontal torso slices (shoulder..hip only; flare rows rejected)
  4. per slice: front WIDTH + side DEPTH -> ellipse girth
  5. pick bust / underbust / waist / hip from slice-curve extrema
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.common.mask_ops import clean_mask as _clean_mask

# Anthropometric landmark heights as fraction of stature measured FROM THE FLOOR.
# (population averages; good enough to locate horizontal measurement lines)
LANDMARK_FROM_FLOOR = {
    "shoulder": 0.818,
    "bust": 0.720,
    "underbust": 0.685,
    "waist": 0.620,
    "hip": 0.530,
}


@dataclass
class LevelMeasure:
    name: str
    y_px: int
    width_cm: float
    depth_cm: float | None
    girth_cm: float | None
    confidence: float


@dataclass
class MarkerlessResult:
    height_cm: float
    weight_kg: float
    bmi: float
    cm_per_px_front: float
    cm_per_px_side: float | None
    levels: list[LevelMeasure] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _segment_grabcut(img: np.ndarray) -> np.ndarray:
    """Fallback: GrabCut person silhouette (used only if MediaPipe unavailable)."""
    h, w = img.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    rect = (int(w * 0.06), int(h * 0.02), int(w * 0.88), int(h * 0.96))
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(img, mask, rect, bgd, fgd, 5, cv2.GC_INIT_WITH_RECT)
    except cv2.error:
        m = np.zeros((h, w), np.uint8)
        m[rect[1] : rect[1] + rect[3], rect[0] : rect[0] + rect[2]] = 255
        return m
    person = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    person = cv2.morphologyEx(person, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8), 2)
    return person


_POSE_MODEL = ROOT / "models" / "pose_landmarker.task"
# MediaPipe Tasks PoseLandmarker index -> name
_POSE_IDX = {
    "nose": 0,
    "l_shoulder": 11,
    "r_shoulder": 12,
    "l_hip": 23,
    "r_hip": 24,
    "l_ankle": 27,
    "r_ankle": 28,
    "l_heel": 29,
    "r_heel": 30,
    "l_foot": 31,
    "r_foot": 32,
}
def _resolve_capture_path(path: str | Path) -> tuple[Path, str | None]:
    """Prefer camera JPG over derived PNG when both exist (PNG breaks MediaPipe pose)."""
    p = Path(path)
    if p.suffix.lower() == ".png":
        jpg = p.with_suffix(".jpg")
        if jpg.is_file():
            return jpg, f"used_jpg_sibling:{jpg.name}"
    return p, None


def _decode_pose_worker_payload(data: dict, img_shape: tuple[int, int], scale: float = 1.0):
    import base64

    landmarks = None
    raw_lm = data.get("landmarks")
    if raw_lm:
        landmarks = {
            k: (int(v[0] / scale), int(v[1] / scale))
            for k, v in raw_lm.items()
        }
    mask = None
    if data.get("mask_b64"):
        arr = cv2.imdecode(
            np.frombuffer(base64.b64decode(data["mask_b64"]), dtype=np.uint8),
            cv2.IMREAD_GRAYSCALE,
        )
        if arr is not None:
            if scale != 1.0:
                h, w = img_shape[:2]
                mask = cv2.resize(arr, (w, h), interpolation=cv2.INTER_LINEAR)
            else:
                mask = arr
    return landmarks, mask


def _run_pose_landmarker_subprocess(bgr: np.ndarray) -> tuple[dict | None, str | None]:
    """macOS: isolate MediaPipe in a child process (pyrender/GL crash workaround)."""
    import os
    import subprocess
    import tempfile

    ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok:
        return None, "encode_failed"
    tmppath: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(buf.tobytes())
            tmppath = tmp.name
        proc = subprocess.run(
            [sys.executable, "-m", "pipeline.measure.pose_worker", tmppath],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=120,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "worker_failed")[:240]
            return None, err
        return json.loads(proc.stdout.strip()), None
    finally:
        if tmppath:
            try:
                os.unlink(tmppath)
            except OSError:
                pass


def _run_pose_landmarker(img: np.ndarray):
    """Run Tasks PoseLandmarker once; returns (landmarks_dict_or_None, mask_or_None)."""
    import platform

    from pipeline.measure.pose_worker import run_on_bgr

    use_subprocess = platform.system() == "Darwin"

    def _call(bgr: np.ndarray, scale: float) -> tuple[dict | None, str | None]:
        del scale
        if use_subprocess:
            return _run_pose_landmarker_subprocess(bgr)
        data = run_on_bgr(bgr)
        if data.get("error"):
            return None, str(data["error"])
        return data, None

    last_err = "no_pose"
    for scale in (1.0, 0.75):
        bgr = img if scale == 1.0 else cv2.resize(
            img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA,
        )
        try:
            data, err = _call(bgr, scale)
        except Exception as e:  # noqa: BLE001
            data, err = None, str(e)
        if not data or data.get("error"):
            continue
        landmarks, mask = _decode_pose_worker_payload(data, img.shape, scale)
        if landmarks or mask is not None:
            return landmarks, mask
        if err:
            last_err = err
        else:
            last_err = data.get("error", "no_pose")
    return None, f"pose_error:{last_err}"


def analyze_view(img: np.ndarray) -> tuple[np.ndarray, dict | None, str | None]:
    """Return (clean person mask, pose landmarks, warning)."""
    landmarks, mask = _run_pose_landmarker(img)
    warn = None
    if isinstance(mask, str):
        warn = mask
        mask = None
    if mask is None:
        mask = _segment_grabcut(img)
        warn = warn or "segmentation_fallback_grabcut"
    return _clean_mask(mask), landmarks, warn


def _vertical_extent(mask: np.ndarray) -> tuple[int, int]:
    ys = np.where(mask.any(axis=1))[0]
    return (int(ys.min()), int(ys.max())) if len(ys) else (0, mask.shape[0] - 1)


def _runs(row: np.ndarray) -> list[tuple[int, int]]:
    on = np.where(row > 0)[0]
    if len(on) == 0:
        return []
    splits = np.where(np.diff(on) > 1)[0]
    groups = np.split(on, splits + 1)
    return [(int(g[0]), int(g[-1])) for g in groups if len(g) > 0]


def _central_run_width(mask: np.ndarray, y: int, cx: int, bounds: tuple[int, int] | None = None) -> int:
    """
    Torso width at row y. If `bounds` (xmin,xmax from pose shoulder/hip span) is
    given, the silhouette is clipped to that range so OUT-STRETCHED ARMS are
    excluded; otherwise falls back to the run containing the body center.
    """
    row = mask[int(np.clip(y, 0, mask.shape[0] - 1))].copy()
    if bounds is not None:
        x0, x1 = max(0, bounds[0]), min(len(row), bounds[1])
        clipped = np.zeros_like(row)
        clipped[x0:x1] = row[x0:x1]
        runs = _runs(clipped)
        if runs:
            a, b = max(runs, key=lambda r: r[1] - r[0])
            return b - a
    runs = _runs(row)
    if not runs:
        return 0
    for a, b in runs:
        if a <= cx <= b:
            return b - a
    a, b = max(runs, key=lambda r: r[1] - r[0])
    return b - a


def _torso_x_bounds(pose: dict | None, y: int, margin: float = 1.30) -> tuple[int, int] | None:
    """X-range of the torso at row y, interpolated from shoulder & hip landmarks."""
    if not pose:
        return None
    sx = sorted([pose["l_shoulder"][0], pose["r_shoulder"][0]])
    hx = sorted([pose["l_hip"][0], pose["r_hip"][0]])
    sy = (pose["l_shoulder"][1] + pose["r_shoulder"][1]) / 2.0
    hy = (pose["l_hip"][1] + pose["r_hip"][1]) / 2.0
    t = 0.0 if hy == sy else (y - sy) / (hy - sy)
    t = float(np.clip(t, -0.25, 1.4))
    left = sx[0] + t * (hx[0] - sx[0])
    right = sx[1] + t * (hx[1] - sx[1])
    cx = (left + right) / 2.0
    half = (right - left) / 2.0 * margin
    return int(cx - half), int(cx + half)


def _largest_run_width(mask: np.ndarray, y: int) -> int:
    runs = _runs(mask[int(np.clip(y, 0, mask.shape[0] - 1))])
    if not runs:
        return 0
    a, b = max(runs, key=lambda r: r[1] - r[0])
    return b - a


def _ellipse_girth_cm(width_cm: float, depth_cm: float) -> float:
    a, b = width_cm / 2.0, depth_cm / 2.0
    return float(np.pi * (3 * (a + b) - np.sqrt(max(0.0, (3 * a + b) * (a + 3 * b)))))


@dataclass
class _ProfileView:
    label: str
    mask: np.ndarray
    pose: dict | None
    top: int
    bottom: int
    cm_per_px: float | None


def _load_profile_view(
    path: str | Path,
    label: str,
    height_cm: float | None,
    ref_kind: str | None,
    ref_marker_mm: float,
    res: MarkerlessResult,
) -> _ProfileView | None:
    resolved, note = _resolve_capture_path(path)
    if note:
        res.warnings.append(f"{label}:{note}")
    img = cv2.imread(str(resolved), cv2.IMREAD_COLOR)
    if img is None:
        res.warnings.append(f"{label}_unreadable")
        return None
    mask, pose, warn = analyze_view(img)
    if warn:
        res.warnings.append(f"{label}:{warn}")
    top, bottom = _vertical_extent(mask)
    stat_px = max(1, bottom - top)
    cm_per_px: float | None
    if ref_kind:
        from pipeline.measure.scale_reference import detect_scale

        sr = detect_scale(img, ref_kind, ref_marker_mm)
        if sr.cm_per_px:
            cm_per_px = sr.cm_per_px
            res.warnings.append(f"{label}_scale:{sr.method}")
        elif height_cm:
            cm_per_px = height_cm / stat_px
            res.warnings.append(f"{label}_ref_failed:{sr.warning};used_height")
        else:
            cm_per_px = None
            res.warnings.append(f"{label}_ref_failed:{sr.warning}")
    else:
        cm_per_px = height_cm / stat_px if height_cm else None
    return _ProfileView(label, mask, pose, top, bottom, cm_per_px)


def _profile_depth_cm(
    profile: _ProfileView,
    floor_frac: float,
    name: str,
    level_y_fn,
) -> float | None:
    """Side depth = full silhouette width on that row (front-back thickness).

    Do not use ``_torso_x_bounds`` here: that helper clips arms on frontal views, but
    on a true side profile shoulder/hip x-coordinates collapse and the bounds slice
    away almost the entire body (depth under-reads by ~5×).
    """
    if profile.label != "side" or not profile.cm_per_px:
        return None
    stat_px = max(1, profile.bottom - profile.top)
    ys = level_y_fn(profile.top, stat_px, profile.pose, floor_frac, name)
    depth_px = _largest_run_width(profile.mask, ys)
    return depth_px * profile.cm_per_px if depth_px > 0 else None


def estimate(
    front_path: str | Path,
    side_path: str | Path | None,
    height_cm: float | None,
    weight_kg: float | None,
    debug_dir: Path | None = None,
    ref_kind: str | None = None,
    ref_marker_mm: float = 50.0,
    back_path: str | Path | None = None,
) -> MarkerlessResult:
    """
    Estimate body girths.

    Scale source (one required):
      - height_cm: scale from the subject's stature, OR
      - ref_kind ('aruco'|'card'|'a4'): scale from a known object in the frame.
    weight_kg is optional (used only for BMI reporting).
    """
    front_resolved, front_note = _resolve_capture_path(front_path)
    if front_note:
        pass  # appended after MarkerlessResult exists
    front = cv2.imread(str(front_resolved), cv2.IMREAD_COLOR)
    if front is None:
        raise FileNotFoundError(front_path)
    if height_cm is None and ref_kind is None:
        raise ValueError("Need a scale source: pass height_cm or ref_kind (aruco/card/a4).")
    bmi = (weight_kg / (height_cm / 100.0) ** 2) if (weight_kg and height_cm) else 0.0
    res = MarkerlessResult(
        height_cm=height_cm or 0.0, weight_kg=weight_kg or 0.0, bmi=round(bmi, 1),
        cm_per_px_front=0.0, cm_per_px_side=None,
    )
    if front_note:
        res.warnings.append(f"front:{front_note}")

    fmask, fpose, fwarn = analyze_view(front)
    if fwarn:
        res.warnings.append(f"front:{fwarn}")
    ft, fb = _vertical_extent(fmask)
    f_stat_px = max(1, fb - ft)
    fcx = int(np.median(np.where(fmask.any(axis=0))[0]))

    # ---- Scale: reference object takes priority over height ----
    if ref_kind:
        from pipeline.measure.scale_reference import detect_scale

        sr = detect_scale(front, ref_kind, ref_marker_mm)
        if sr.cm_per_px:
            res.cm_per_px_front = sr.cm_per_px
            res.warnings.append(f"front_scale:{sr.method}")
        elif height_cm:
            res.cm_per_px_front = height_cm / f_stat_px
            res.warnings.append(f"front_ref_failed:{sr.warning};used_height")
        else:
            res.warnings.append(f"front_ref_failed:{sr.warning}")
            res.cm_per_px_front = 0.0
    else:
        res.cm_per_px_front = height_cm / f_stat_px

    profiles: list[_ProfileView] = []
    for label, path in (("side", side_path), ("back", back_path)):
        if path:
            pv = _load_profile_view(path, label, height_cm, ref_kind, ref_marker_mm, res)
            if pv:
                profiles.append(pv)
    side_scales = [p.cm_per_px for p in profiles if p.cm_per_px]
    res.cm_per_px_side = float(np.mean(side_scales)) if side_scales else None
    if not profiles:
        res.warnings.append("no_profile_views_depth_estimated_from_width")
    if fpose is None:
        res.warnings.append("pose_not_detected_slice_sweep_degraded")

    side_pv = next((p for p in profiles if p.label == "side"), None)
    from pipeline.measure.slice_measure import estimate_torso_girths

    samples, girth_levels, sweep_warn = estimate_torso_girths(
        fmask, fpose, fcx, res.cm_per_px_front, side_pv, res.cm_per_px_side,
    )
    res.warnings.extend(sweep_warn)

    if len(girth_levels) >= 3:
        res.levels = girth_levels
    else:
        res.warnings.append("slice_sweep:fallback_fixed_landmarks")
        res.levels = _estimate_fixed_landmarks(
            front, fmask, fpose, ft, fb, f_stat_px, fcx, res, profiles,
        )

    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        ov = front.copy()
        for s in samples:
            color = (0, 0, 255) if s.flare else (80, 80, 80)
            cv2.line(ov, (0, s.y), (ov.shape[1], s.y), color, 1)
        for lv in res.levels:
            cv2.line(ov, (0, lv.y_px), (ov.shape[1], lv.y_px), (255, 0, 255), 2)
            cv2.putText(ov, f"{lv.name} {lv.girth_cm}cm", (10, lv.y_px - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 180, 0), 2)
        cv2.imwrite(str(debug_dir / "markerless_front.jpg"), ov)
        cv2.imwrite(str(debug_dir / "markerless_front_mask.png"), fmask)
        for pv in profiles:
            cv2.imwrite(str(debug_dir / f"markerless_{pv.label}_mask.png"), pv.mask)
        if samples:
            (debug_dir / "slice_sweep.json").write_text(json.dumps(
                [{"y": s.y, "frac": round(s.torso_frac, 3), "width_cm": round(s.width_cm, 1),
                  "depth_cm": round(s.depth_cm, 1) if s.depth_cm else None,
                  "girth_cm": round(s.girth_cm, 1), "flare": s.flare} for s in samples],
                indent=2,
            ))
    return res


def _estimate_fixed_landmarks(
    front,
    fmask,
    fpose,
    ft,
    fb,
    f_stat_px,
    fcx,
    res,
    profiles,
) -> list[LevelMeasure]:
    """Legacy fixed-landmark ellipse estimator (fallback when slice sweep fails)."""

    def level_y(mask_top, stat_px, pose, floor_frac, name):
        if pose:
            sh_y = (pose["l_shoulder"][1] + pose["r_shoulder"][1]) / 2
            hip_y = (pose["l_hip"][1] + pose["r_hip"][1]) / 2
            torso = hip_y - sh_y
            anchors = {
                "shoulder": sh_y,
                "bust": sh_y + 0.30 * torso,
                "underbust": sh_y + 0.50 * torso,
                "waist": sh_y + 0.75 * torso,
                "hip": hip_y + 0.12 * torso,
            }
            return int(anchors[name])
        return int(mask_top + (1.0 - floor_frac) * stat_px)

    levels: list[LevelMeasure] = []
    for name, floor_frac in LANDMARK_FROM_FLOOR.items():
        if name == "shoulder":
            continue
        yf = level_y(ft, f_stat_px, fpose, floor_frac, name)
        fbounds = _torso_x_bounds(fpose, yf)
        width_px = _central_run_width(fmask, yf, fcx, fbounds)
        width_cm = width_px * res.cm_per_px_front
        depth_cm = None
        girth = None
        if profiles:
            depths = [
                d for p in profiles
                if (d := _profile_depth_cm(p, floor_frac, name, level_y)) is not None and d > 1
            ]
            if depths:
                depth_cm = float(np.mean(depths))
                if depth_cm < 0.45 * width_cm or depth_cm > 0.90 * width_cm:
                    depth_cm = None
        if width_cm > 1:
            if depth_cm and depth_cm > 1:
                girth = _ellipse_girth_cm(width_cm, depth_cm)
            else:
                girth = _ellipse_girth_cm(width_cm, 0.72 * width_cm)
        conf = 0.6 if (fpose and depth_cm and depth_cm > 1) else 0.35
        levels.append(
            LevelMeasure(
                name=name,
                y_px=yf,
                width_cm=round(width_cm, 1),
                depth_cm=round(depth_cm, 1) if depth_cm else None,
                girth_cm=round(girth, 1) if girth else None,
                confidence=conf,
            )
        )
    return levels


def _raw_girths(res: MarkerlessResult) -> dict[str, float]:
    from pipeline.measure.calibration import GIRTH_LEVELS

    return {
        lv.name: lv.girth_cm
        for lv in res.levels
        if lv.name in GIRTH_LEVELS and lv.girth_cm is not None
    }


def print_report(res: MarkerlessResult, calibrated: dict[str, float] | None = None) -> None:
    print(f"\n{'#' * 56}")
    print("  MARKERLESS BODY MEASUREMENTS (approximate)")
    print(f"{'#' * 56}")
    print(f"  Height {res.height_cm:.0f} cm | Weight {res.weight_kg:.0f} kg | BMI {res.bmi}")
    print(f"  Scale: front {res.cm_per_px_front:.4f} cm/px"
          + (f", side {res.cm_per_px_side:.4f} cm/px" if res.cm_per_px_side else " (no side)"))
    if res.warnings:
        print(f"  Warnings: {', '.join(res.warnings)}")
    print(f"  {'level':10} {'width':>8} {'depth':>8} {'girth':>9}  conf")
    for lv in res.levels:
        d = f"{lv.depth_cm:8.1f}" if lv.depth_cm is not None else f"{'--':>8}"
        g = f"{lv.girth_cm:9.1f}" if lv.girth_cm is not None else f"{'--':>9}"
        print(f"  {lv.name:10} {lv.width_cm:8.1f} {d} {g}  {lv.confidence:.2f}")
    if calibrated:
        print(f"  --- tape-calibrated girths (cm / in) ---")
        for k in ("bust", "underbust", "waist", "hip"):
            if k in calibrated:
                print(f"  {k:10} {calibrated[k]:8.1f} {calibrated[k] / 2.54:9.1f}")
    print(f"{'#' * 56}")


def main() -> None:
    p = argparse.ArgumentParser(description="Markerless body measurements from front+side photos")
    p.add_argument("front", type=Path)
    p.add_argument("side", type=Path, nargs="?", default=None)
    p.add_argument("--height", type=float, default=None, help="height in cm (or use --ref)")
    p.add_argument("--weight", type=float, default=None, help="weight in kg (optional)")
    p.add_argument("--ref", choices=("aruco", "card", "a4"), default=None,
                   help="reference object in frame for scale (instead of height)")
    p.add_argument("--ref-mm", type=float, default=50.0, help="ArUco marker side length (mm)")
    p.add_argument("--tape-in", type=str, default=None,
                   help="tape anchors in inches, e.g. bust=44,waist=38 (fits calibration)")
    p.add_argument("--tape-cm", type=str, default=None, help="tape anchors in cm")
    p.add_argument("--calibration", type=Path, default=None,
                   help="JSON profile from pipeline.measure.calibration fit")
    p.add_argument("--debug-dir", type=Path, default=None)
    args = p.parse_args()
    if args.height is None and args.ref is None:
        p.error("provide --height or --ref (aruco/card/a4)")
    res = estimate(args.front, args.side, args.height, args.weight, args.debug_dir,
                   ref_kind=args.ref, ref_marker_mm=args.ref_mm)
    calibrated = None
    cal_profile = None
    raw_g = _raw_girths(res)
    if args.calibration:
        from pipeline.measure.calibration import apply_girth_calibration, load_profile

        cal_profile = load_profile(args.calibration)
        calibrated = apply_girth_calibration(raw_g, cal_profile)
    elif args.tape_in or args.tape_cm:
        from pipeline.measure.calibration import apply_girth_calibration, fit_profile, parse_tape_spec

        anchors = parse_tape_spec(args.tape_cm or args.tape_in, unit="cm" if args.tape_cm else "in")
        cal_profile = fit_profile(anchors, raw_g, name="inline")
        calibrated = apply_girth_calibration(raw_g, cal_profile)
    print_report(res, calibrated=calibrated)
    out = args.debug_dir / "markerless_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "height_cm": res.height_cm, "weight_kg": res.weight_kg, "bmi": res.bmi,
        "cm_per_px_front": res.cm_per_px_front, "cm_per_px_side": res.cm_per_px_side,
        "warnings": res.warnings,
        "levels": [vars(lv) for lv in res.levels],
        "girths_raw_cm": raw_g,
    }
    if calibrated:
        payload["girths_calibrated_cm"] = calibrated
        payload["girths_calibrated_in"] = {k: round(v / 2.54, 1) for k, v in calibrated.items()}
    if cal_profile:
        payload["calibration"] = cal_profile.to_dict()
    out.write_text(json.dumps(payload, indent=2))
    print(f"\nSaved: {out}")
    print(f"Overlay: {args.debug_dir}/markerless_front.jpg")


if __name__ == "__main__":
    main()
