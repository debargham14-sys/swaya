"""
OpenCV helpers for the DSV measurement probe notebook.

Loads front / back / side captures, places anatomical + DSV measurement lines,
detects magenta bands & ArUco scale, and computes girths from silhouette width
+ side depth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

# Standard Swaya DSV measurement levels (top -> bottom)
LEVELS = ("neck", "shoulder", "bust", "underbust", "waist", "hip", "hem")
# Dark, high-contrast BGR (visible on light clothing / walls)
LEVEL_COLORS_BGR = {
    "neck": (0, 140, 220),
    "shoulder": (0, 100, 200),
    "bust": (180, 0, 180),
    "underbust": (160, 0, 140),
    "waist": (0, 120, 0),
    "hip": (0, 90, 200),
    "hem": (0, 80, 160),
}
_LINE_THICK = 4
_TRAP_THICK = 4
_SHOULDER_WIDTH_THICK = 5
_OUTLINE_BGR = (20, 20, 20)

# Magenta print on DSV panels (HSV)
_MAGENTA_LO = np.array([140, 60, 60], np.uint8)
_MAGENTA_HI = np.array([175, 255, 255], np.uint8)


@dataclass
class ViewData:
    name: str
    path: Path
    bgr: np.ndarray
    mask: np.ndarray  # refined — overlay / visualization only
    pose: dict[str, tuple[float, float]] | None
    warnings: list[str] = field(default_factory=list)
    cm_per_px: float = 0.0
    scale_method: str = ""
    magenta_rows: list[int] = field(default_factory=list)
    top_px: int = 0
    bottom_px: int = 0
    mask_raw: np.ndarray | None = None  # raw segmentation — used for scale + girths


@dataclass
class LineMeasure:
    level: str
    y_front: int | None
    y_side: int | None
    y_back: int | None
    width_cm: float | None
    depth_cm: float | None
    girth_cm: float | None
    source: str = "manual"


@dataclass
class ShoulderMeasure:
    """Trapezius (neck base → shoulder tip) and shoulder width on one view."""

    view: str
    neck_px: tuple[float, float]
    l_shoulder_px: tuple[float, float]
    r_shoulder_px: tuple[float, float]
    shoulder_width_cm: float | None
    trap_left_cm: float | None
    trap_right_cm: float | None
    shoulder_slope_deg_l: float | None
    shoulder_slope_deg_r: float | None


from pipeline.measure.body_profile import (  # noqa: E402
    BodyProfile,
    CaptureHints,
    detect_clothing,
    estimate_torso_girths_profiled,
    profile_notes,
    torso_fracs,
)

_GIRTH_LEVELS = frozenset(("bust", "underbust", "waist", "hip"))


def _px_dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))


def _line_slope_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    return float(np.degrees(np.arctan2(dy, dx)))


def shoulder_points(
    pose: dict[str, tuple[float, float]] | None,
    neck_y: int,
    shoulder_y: int,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]] | None:
    """Neck base (mid) + left/right shoulder tips using pose X and slider Y."""
    if not pose or "l_shoulder" not in pose or "r_shoulder" not in pose:
        return None
    lx, _ = pose["l_shoulder"]
    rx, _ = pose["r_shoulder"]
    neck = ((lx + rx) / 2.0, float(neck_y))
    l_sh = (float(lx), float(shoulder_y))
    r_sh = (float(rx), float(shoulder_y))
    return neck, l_sh, r_sh


def compute_shoulder_measurements(
    views: dict[str, ViewData],
    level_ys: dict[str, dict[str, int]],
) -> list[ShoulderMeasure]:
    """Shoulder width + trapezius lengths on front/back (both shoulders) and side."""
    out: list[ShoulderMeasure] = []
    for vname in ("front", "back", "side"):
        vd = views.get(vname)
        if not vd or not vd.pose:
            continue
        ys = level_ys.get(vname, {})
        neck_y = ys.get("neck")
        sh_y = ys.get("shoulder")
        if neck_y is None or sh_y is None:
            continue
        pts = shoulder_points(vd.pose, neck_y, sh_y)
        if not pts:
            continue
        neck, l_sh, r_sh = pts
        cpp = _cpp_width(vd)
        if cpp <= 0:
            continue
        trap_l = round(_px_dist(neck, l_sh) * cpp, 2)
        trap_r = round(_px_dist(neck, r_sh) * cpp, 2)
        width = round(_px_dist(l_sh, r_sh) * cpp, 2)
        # Side profile: far shoulder often occluded — report visible trap only
        if vname == "side":
            visible = trap_l if l_sh[0] < neck[0] else trap_r
            out.append(
                ShoulderMeasure(
                    view=vname,
                    neck_px=neck,
                    l_shoulder_px=l_sh,
                    r_shoulder_px=r_sh,
                    shoulder_width_cm=None,
                    trap_left_cm=trap_l,
                    trap_right_cm=trap_r,
                    shoulder_slope_deg_l=round(_line_slope_deg(neck, l_sh), 1),
                    shoulder_slope_deg_r=round(_line_slope_deg(neck, r_sh), 1),
                )
            )
            _ = visible
        else:
            out.append(
                ShoulderMeasure(
                    view=vname,
                    neck_px=neck,
                    l_shoulder_px=l_sh,
                    r_shoulder_px=r_sh,
                    shoulder_width_cm=width,
                    trap_left_cm=trap_l,
                    trap_right_cm=trap_r,
                    shoulder_slope_deg_l=round(_line_slope_deg(neck, l_sh), 1),
                    shoulder_slope_deg_r=round(_line_slope_deg(neck, r_sh), 1),
                )
            )
    return out


def best_shoulder_width(shoulders: list[ShoulderMeasure]) -> float | None:
    """Prefer back view shoulder span, else front."""
    for prefer in ("back", "front"):
        for s in shoulders:
            if s.view == prefer and s.shoulder_width_cm:
                return s.shoulder_width_cm
    return None


def _import_markerless():
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from pipeline.measure import markerless as ml

    return ml


def load_image(path: str | Path) -> np.ndarray:
    p = Path(path)
    img = cv2.imread(str(p), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(p)
    return img


def _clip_mask_to_torso_column(mask: np.ndarray, pose: dict) -> np.ndarray:
    """Zero silhouette outside pose shoulder→hip span per row (drops arms/skirt wings)."""
    ml = _import_markerless()
    h, w = mask.shape[:2]
    out = np.zeros_like(mask)
    sh = (pose["l_shoulder"][1] + pose["r_shoulder"][1]) / 2.0
    hip = (pose["l_hip"][1] + pose["r_hip"][1]) / 2.0
    y0, y1 = int(max(0, sh - 0.05 * (hip - sh))), int(min(h, hip + 0.08 * (hip - sh)))
    for y in range(y0, y1):
        bounds = ml._torso_x_bounds(pose, y, margin=1.05)
        if not bounds:
            continue
        x0, x1 = max(0, bounds[0]), min(w, bounds[1])
        out[y, x0:x1] = mask[y, x0:x1]
    return out


def refine_body_mask(mask: np.ndarray, pose: dict | None, view: str) -> np.ndarray:
    """Denoise silhouette: morphology, median blur, torso clip, skirt suppression."""
    from pipeline.common.mask_ops import clean_mask

    m = clean_mask(mask)
    m = cv2.medianBlur(m, 5)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((13, 13), np.uint8), iterations=1)
    if pose:
        hy = int((pose["l_hip"][1] + pose["r_hip"][1]) / 2)
        if view == "side":
            # Profile: do not column-clip (shoulder/hip share x); only trim skirt flare
            below = m[hy:, :].copy()
            below = cv2.erode(below, np.ones((9, 5), np.uint8), iterations=1)
            m[hy:, :] = below
        else:
            m = _clip_mask_to_torso_column(m, pose)
            below = m[hy:, :].copy()
            below = cv2.erode(below, np.ones((11, 7), np.uint8), iterations=2)
            m[hy:, :] = below
    return clean_mask(m)


def analyze_view(name: str, path: str | Path) -> ViewData:
    ml = _import_markerless()
    bgr = load_image(path)
    mask_raw, pose, warn = ml.analyze_view(bgr)
    top, bot = _vertical_extent(mask_raw)
    mask_vis = refine_body_mask(mask_raw, pose, name)
    magenta = detect_magenta_rows(bgr)
    warnings = [warn] if warn else []
    warnings.append("mask:refined_display_only")
    return ViewData(
        name=name,
        path=Path(path),
        bgr=bgr,
        mask=mask_vis,
        mask_raw=mask_raw,
        pose=pose,
        warnings=warnings,
        top_px=top,
        bottom_px=bot,
        magenta_rows=magenta,
    )


def _meas_mask(view: ViewData) -> np.ndarray:
    return view.mask_raw if view.mask_raw is not None else view.mask


def unify_scales(views: dict[str, ViewData]) -> float | None:
    """Match API: front scale for width; mean side/back scale for depth."""
    front = views.get("front")
    if not front or front.cm_per_px <= 0:
        return None
    profile_scales = [
        v.cm_per_px for k, v in views.items() if k in ("side", "back") and v.cm_per_px > 0
    ]
    side_cpp = float(np.mean(profile_scales)) if profile_scales else front.cm_per_px
    front.cm_per_px_width = front.cm_per_px  # type: ignore[attr-defined]
    for v in views.values():
        v.cm_per_px_width = front.cm_per_px  # type: ignore[attr-defined]
        v.cm_per_px_depth = side_cpp  # type: ignore[attr-defined]
    return side_cpp


def _vertical_extent(mask: np.ndarray) -> tuple[int, int]:
    rows = np.where(mask.any(axis=1))[0]
    if len(rows) == 0:
        h = mask.shape[0]
        return 0, h - 1
    return int(rows[0]), int(rows[-1])


def detect_magenta_rows(bgr: np.ndarray, min_width_frac: float = 0.15) -> list[int]:
    """Horizontal magenta band centre-rows (printed DSV measurement lines)."""
    h, w = bgr.shape[:2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mag = cv2.inRange(hsv, _MAGENTA_LO, _MAGENTA_HI)
    mag = cv2.morphologyEx(mag, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    min_run = int(w * min_width_frac)
    rows: list[tuple[int, int]] = []
    for y in range(h):
        runs = _runs(mag[y])
        if any(b - a >= min_run for a, b in runs):
            rows.append((y, sum(b - a for a, b in runs)))
    if not rows:
        return []
    # cluster adjacent rows into bands, keep band centres
    bands: list[list[int]] = []
    cur = [rows[0][0]]
    for y, _ in rows[1:]:
        if y - cur[-1] <= 4:
            cur.append(y)
        else:
            bands.append(cur)
            cur = [y]
    bands.append(cur)
    return [int(np.median(b)) for b in bands]


def _runs(row: np.ndarray) -> list[tuple[int, int]]:
    on = np.where(row > 0)[0]
    if len(on) == 0:
        return []
    splits = np.where(np.diff(on) > 1)[0]
    groups = np.split(on, splits + 1)
    return [(int(g[0]), int(g[-1]) + 1) for g in groups]


def calibrate_scale(
    view: ViewData,
    height_cm: float | None = None,
    ref_kind: str | None = None,
    ref_marker_mm: float = 50.0,
    aruco_marker_mm: float = 18.0,
) -> None:
    """Set view.cm_per_px from DSV ArUco, generic ref object, or stature."""
    from pipeline.measure.scale_reference import detect_scale

    stat = max(1, view.bottom_px - view.top_px)
    if ref_kind:
        sr = detect_scale(view.bgr, ref_kind, ref_marker_mm)
        if sr.cm_per_px:
            view.cm_per_px = sr.cm_per_px
            view.scale_method = f"ref:{sr.method}"
            return
    # DSV shoulder/window ArUco markers (18 mm in print spec)
    sr = detect_scale(view.bgr, "aruco", aruco_marker_mm)
    if sr.cm_per_px:
        view.cm_per_px = sr.cm_per_px
        view.scale_method = "dsv_aruco"
        return
    if height_cm:
        view.cm_per_px = height_cm / stat
        view.scale_method = "height_stature"
        return
    view.scale_method = "none"
    view.cm_per_px = 0.0


def default_level_y(
    view: ViewData,
    level: str,
    magenta_rows: list[int] | None = None,
) -> int:
    """Initial Y for a measurement line: magenta bands > pose > anthropometric."""
    ml = _import_markerless()
    stat = max(1, view.bottom_px - view.top_px)
    pose = view.pose

    # Map magenta band count to levels when DSV lines are visible
    mags = sorted(magenta_rows or view.magenta_rows)
    mag_map = {}
    if len(mags) >= 3:
        names = ("bust", "underbust", "waist")
        for nm, y in zip(names, mags[-3:]):
            mag_map[nm] = y
    if level in mag_map:
        return mag_map[level]

    if pose:
        sh_y = (pose["l_shoulder"][1] + pose["r_shoulder"][1]) / 2
        hip_y = (pose["l_hip"][1] + pose["r_hip"][1]) / 2
        torso = hip_y - sh_y
        if level == "neck":
            return int(sh_y - 0.12 * torso)
        if level == "shoulder":
            return int(sh_y)
        if level == "bust":
            return int(sh_y + 0.30 * torso)
        if level == "underbust":
            return int(sh_y + 0.50 * torso)
        if level == "waist":
            return int(sh_y + 0.95 * torso)
        if level == "hip":
            return int(hip_y + 0.10 * torso)
        if level == "hem":
            return int(view.bottom_px - 0.02 * stat)

    frac = ml.LANDMARK_FROM_FLOOR.get(level, 0.65)
    if level == "neck":
        frac = 0.88
    if level == "hem":
        return int(view.bottom_px - 0.03 * stat)
    return int(view.top_px + (1.0 - frac) * stat)


def _torso_frac(pose: dict, y: int) -> float:
    sh = (pose["l_shoulder"][1] + pose["r_shoulder"][1]) / 2.0
    hip = (pose["l_hip"][1] + pose["r_hip"][1]) / 2.0
    return float(np.clip((y - sh) / max(1.0, hip - sh), 0.0, 1.2))


def _y_from_torso_frac(pose: dict, frac: float) -> int:
    sh = (pose["l_shoulder"][1] + pose["r_shoulder"][1]) / 2.0
    hip = (pose["l_hip"][1] + pose["r_hip"][1]) / 2.0
    return int(sh + frac * (hip - sh))


def _snap_levels_from_slice_sweep(views: dict[str, ViewData], level_ys: dict[str, dict[str, int]]) -> None:
    """Use API slice-sweep on raw front mask to place waist/hip/bust rows."""
    front = views.get("front")
    if not front or not front.pose or front.cm_per_px <= 0:
        return
    ml = _import_markerless()
    from pipeline.measure.slice_measure import levels_from_sweep, scan_torso_slices

    fmask = _meas_mask(front)
    fcx = int(np.median(np.where(fmask.any(axis=0))[0])) if fmask.any() else fmask.shape[1] // 2
    side = views.get("side")
    side_cpp = getattr(side, "cm_per_px_depth", side.cm_per_px if side else None) if side else None
    side_pv = None
    if side and side.pose:
        side_pv = ml._ProfileView(
            label="side",
            mask=_meas_mask(side),
            pose=side.pose,
            top=side.top_px,
            bottom=side.bottom_px,
            cm_per_px=side_cpp,
        )
    samples, sweep_warn = scan_torso_slices(
        fmask, front.pose, fcx, front.cm_per_px, side_pv, side_cpp,
    )
    front.warnings.extend(sweep_warn)
    girth_levels, lvl_warn = levels_from_sweep(samples)
    front.warnings.extend(lvl_warn)
    for lv in girth_levels:
        if lv.name not in LEVELS:
            continue
        frac = _torso_frac(front.pose, lv.y_px)
        level_ys.setdefault("front", {})[lv.name] = lv.y_px
        for vname, vd in views.items():
            if vname == "front" or not vd.pose:
                continue
            level_ys.setdefault(vname, {})[lv.name] = _y_from_torso_frac(vd.pose, frac)


def init_level_ys(views: dict[str, ViewData]) -> dict[str, dict[str, int]]:
    """Per-view default Y; waist/hip/bust snapped from raw-mask torso slice-sweep."""
    unify_scales(views)
    out: dict[str, dict[str, int]] = {}
    for vname, vd in views.items():
        vd.magenta_rows = detect_magenta_rows(vd.bgr)
        out[vname] = {lv: default_level_y(vd, lv) for lv in LEVELS}
    _snap_levels_from_slice_sweep(views, out)
    return out


def sync_girth_level_ys(
    views: dict[str, ViewData],
    level_ys: dict[str, dict[str, int]],
    body_profile: BodyProfile | None = None,
    height_cm: float | None = None,
    weight_kg: float | None = None,
) -> dict[str, dict[str, int]]:
    """Align bust/underbust/waist/hip rows with body-profile slice picks."""
    front = views.get("front")
    if not front or not front.pose:
        return level_ys
    api_lv, _, _ = _api_girth_levels(views, body_profile, height_cm, weight_kg)
    for name, lv in api_lv.items():
        if name not in _GIRTH_LEVELS:
            continue
        level_ys.setdefault("front", {})[name] = lv.y_px
        frac = _torso_frac(front.pose, lv.y_px)
        for vname, vd in views.items():
            if vname == "front" or not vd.pose:
                continue
            level_ys.setdefault(vname, {})[name] = _y_from_torso_frac(vd.pose, frac)
    return level_ys


def _row_width_px(
    mask: np.ndarray,
    y: int,
    pose: dict | None,
    cx: int,
    tight: bool = False,
) -> int:
    ml = _import_markerless()
    margin = 1.02 if tight else 1.15
    bounds = ml._torso_x_bounds(pose, y, margin=margin) if pose else None
    return ml._central_run_width(mask, y, cx, bounds)


def _cpp_width(view: ViewData) -> float:
    return getattr(view, "cm_per_px_width", view.cm_per_px)


def _cpp_depth(view: ViewData) -> float:
    return getattr(view, "cm_per_px_depth", view.cm_per_px)


def width_at_row(
    mask: np.ndarray,
    y: int,
    pose: dict | None,
    cm_per_px: float,
    level: str = "",
) -> float | None:
    if cm_per_px <= 0:
        return None
    ml = _import_markerless()
    h = mask.shape[0]
    y = int(np.clip(y, 0, h - 1))
    cx = int(np.median(np.where(mask.any(axis=0))[0])) if mask.any() else mask.shape[1] // 2
    tight = level in ("waist", "hip", "underbust")
    # median of 3 rows reduces segmentation speckle
    widths = [
        _row_width_px(mask, int(np.clip(y + dy, 0, h - 1)), pose, cx, tight=tight)
        for dy in (-1, 0, 1)
    ]
    px = int(np.median([w for w in widths if w > 0])) if any(w > 0 for w in widths) else 0
    return round(px * cm_per_px, 2) if px > 2 else None


def _is_side_profile(pose: dict | None) -> bool:
    """True when shoulders collapse in x (true side view)."""
    if not pose:
        return False
    lx, _ = pose["l_shoulder"]
    rx, _ = pose["r_shoulder"]
    return abs(rx - lx) < 50


def depth_at_row(
    mask: np.ndarray,
    y: int,
    pose: dict | None,
    cm_per_px: float,
    level: str = "",
    *,
    side_view: bool = False,
    width_cm: float | None = None,
) -> float | None:
    if cm_per_px <= 0:
        return None
    from pipeline.measure.slice_measure import _depth_cm_at_y

    ml = _import_markerless()
    h = mask.shape[0]
    y = int(np.clip(y, 0, h - 1))
    profile = side_view or _is_side_profile(pose)
    if profile and width_cm:
        side_pv = ml._ProfileView("side", mask, pose, 0, h - 1, cm_per_px)
        depths = [
            _depth_cm_at_y(side_pv, int(np.clip(y + dy, 0, h - 1)), width_cm)
            for dy in (-1, 0, 1)
        ]
        valid = [d for d in depths if d]
        if valid:
            return round(float(np.median(valid)), 2)
    widths: list[int] = []
    for dy in (-1, 0, 1):
        yrow = int(np.clip(y + dy, 0, h - 1))
        if profile:
            widths.append(ml._largest_run_width(mask, yrow))
        else:
            cx = mask.shape[1] // 2
            tight = level in ("waist", "hip", "underbust")
            widths.append(_row_width_px(mask, yrow, pose, cx, tight=tight))
    px = int(np.median([w for w in widths if w > 0])) if any(w > 0 for w in widths) else 0
    if px <= 2:
        return None
    depth = px * cm_per_px
    if width_cm and (depth < 0.45 * width_cm or depth > 0.78 * width_cm):
        return round(0.68 * width_cm, 2)
    return round(depth, 2)


def ellipse_girth(width_cm: float, depth_cm: float) -> float:
    ml = _import_markerless()
    return round(ml._ellipse_girth_cm(width_cm, depth_cm), 1)


def _capture_hints(views: dict[str, ViewData]) -> CaptureHints:
    front = views.get("front")
    return CaptureHints(
        has_dsv_aruco=any(v.scale_method == "dsv_aruco" for v in views.values()),
        magenta_band_count=max((len(v.magenta_rows) for v in views.values()), default=0),
        mask_bottom_px=front.bottom_px if front else 0,
        pose=front.pose if front else None,
    )


def _api_girth_levels(
    views: dict[str, ViewData],
    body_profile: BodyProfile | None = None,
    height_cm: float | None = None,
    weight_kg: float | None = None,
) -> tuple[dict[str, Any], list[str], str]:
    """Shared pipeline: slice-sweep + body_profile module."""
    front = views.get("front")
    if not front or front.cm_per_px <= 0:
        return {}, [], "none"
    ml = _import_markerless()
    profile = body_profile or BodyProfile()
    fmask = _meas_mask(front)
    fcx = int(np.median(np.where(fmask.any(axis=0))[0])) if fmask.any() else fmask.shape[1] // 2
    side = views.get("side")
    side_cpp = getattr(side, "cm_per_px_depth", side.cm_per_px if side else None) if side else None
    side_pv = None
    if side and side.pose:
        side_pv = ml._ProfileView(
            label="side",
            mask=_meas_mask(side),
            pose=side.pose,
            top=side.top_px,
            bottom=side.bottom_px,
            cm_per_px=side_cpp,
        )

    hints = _capture_hints(views)
    samples, girth_levels, diag = estimate_torso_girths_profiled(
        fmask, front.pose, fcx, front.cm_per_px, side_pv, side_cpp,
        profile=profile, hints=hints, height_cm=height_cm, weight_kg=weight_kg,
    )
    front.warnings.extend(diag)
    clothing = detect_clothing(profile, hints, samples)
    if any("body_core_loose" in w for w in diag):
        source_tag = next(w.replace("body_profile:", "") for w in diag if "body_core_" in w)
    elif clothing == "dsv_vest":
        source_tag = "dsv_vest"
    else:
        source_tag = "fitted_silhouette"
    return {lv.name: lv for lv in girth_levels}, diag, source_tag


def apply_tape_calibration(
    measures: list[LineMeasure],
    tape_cm: dict[str, float],
) -> list[LineMeasure]:
    """Affine-fit girths to tape anchors (needs ≥1 matching level)."""
    from pipeline.measure.calibration import apply_girth_calibration, fit_profile

    raw = {
        m.level: m.girth_cm
        for m in measures
        if m.girth_cm and m.level in _GIRTH_LEVELS
    }
    anchors = {k: v for k, v in tape_cm.items() if k in _GIRTH_LEVELS}
    if not raw or not anchors:
        return measures
    try:
        prof = fit_profile(anchors, raw, name="notebook_tape")
        cal = apply_girth_calibration(raw, prof)
    except ValueError:
        return measures

    out: list[LineMeasure] = []
    for m in measures:
        if m.level in cal:
            out.append(
                LineMeasure(
                    level=m.level,
                    y_front=m.y_front,
                    y_side=m.y_side,
                    y_back=m.y_back,
                    width_cm=m.width_cm,
                    depth_cm=m.depth_cm,
                    girth_cm=cal[m.level],
                    source=f"{m.source}+tape_cal",
                )
            )
        else:
            out.append(m)
    return out


def compute_measurements(
    views: dict[str, ViewData],
    level_ys: dict[str, dict[str, int]],
    body_profile: BodyProfile | None = None,
    height_cm: float | None = None,
    weight_kg: float | None = None,
    tape_cm: dict[str, float] | None = None,
    tape_calibrate: bool = False,
) -> list[LineMeasure]:
    unify_scales(views)
    front = views.get("front")
    side = views.get("side")
    back = views.get("back")
    api_lv, _diag, source_tag = _api_girth_levels(views, body_profile, height_cm, weight_kg)
    rows: list[LineMeasure] = []
    for lv in LEVELS:
        yf = level_ys.get("front", {}).get(lv) if front else None
        ys = level_ys.get("side", {}).get(lv) if side else None
        yb = level_ys.get("back", {}).get(lv) if back else None
        if lv in _GIRTH_LEVELS and lv in api_lv and yf is not None:
            al = api_lv[lv]
            if abs(yf - al.y_px) <= 8:
                src = source_tag
                rows.append(
                    LineMeasure(
                        level=lv,
                        y_front=yf,
                        y_side=ys,
                        y_back=yb,
                        width_cm=al.width_cm,
                        depth_cm=al.depth_cm,
                        girth_cm=al.girth_cm,
                        source=src,
                    )
                )
                continue
        fmask = _meas_mask(front) if front else None
        smask = _meas_mask(side) if side else None
        w_cpp = _cpp_width(front) if front else 0.0
        d_cpp = _cpp_depth(side) if side else 0.0
        w = (
            width_at_row(fmask, yf, front.pose, w_cpp, level=lv)
            if front and fmask is not None and yf is not None
            else None
        )
        d = (
            depth_at_row(
                smask, ys, side.pose, d_cpp, level=lv, side_view=True, width_cm=w,
            )
            if side and smask is not None and ys is not None
            else None
        )
        g = None
        src = "width_only"
        if w and d:
            g = ellipse_girth(w, d)
            src = "raw_front+side"
        elif w:
            g = ellipse_girth(w, 0.68 * w)
            src = "raw_width_est_depth"
        rows.append(
            LineMeasure(
                level=lv,
                y_front=yf,
                y_side=ys,
                y_back=yb,
                width_cm=w,
                depth_cm=d,
                girth_cm=g,
                source=src,
            )
        )
    if tape_calibrate and tape_cm:
        rows = apply_tape_calibration(rows, tape_cm)
    return rows


# --- ChArUco rectified measurement (F0–F3 stickers) ---

_CHARUCO_SLOT_BY_VIEW: dict[str, str] = {
    "front": "F1",
    "back": "F3",
}


def orient_view_bgr(name: str, bgr: np.ndarray) -> np.ndarray:
    """Rotate landscape phone captures to portrait (person upright)."""
    if bgr.shape[1] > bgr.shape[0]:
        return cv2.rotate(bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return bgr


def calibrate_scale_charuco(
    view: ViewData,
    slot_name: str,
    stencil_spec_path: Path | None = None,
) -> Any:
    """Set ``view.cm_per_px`` from a decoded ChArUco sticker (F0–F3)."""
    import charuco_dsv_lib as clib

    slots = clib.default_dsv_marker_slots(stencil_spec_path)
    if slot_name not in slots:
        view.warnings.append(f"charuco:unknown_slot:{slot_name}")
        return None
    cal, center_px, _ = clib.find_charuco_slot_in_image(
        view.bgr, slots[slot_name], spec=clib.CharucoRectifySpec()
    )
    if cal.mm_per_px and cal.charuco_corners >= 4:
        view.cm_per_px = cal.mm_per_px / 10.0
        view.scale_method = f"charuco_{slot_name}"
        view.warnings.append(f"charuco:{slot_name}:{cal.charuco_corners}corners")
        setattr(view, "charuco_cal", cal)
        setattr(view, "charuco_slot", slot_name)
        setattr(view, "charuco_center_px", center_px)
        return cal
    view.warnings.append(f"charuco:{slot_name}:only_{cal.charuco_corners}_corners")
    return None


def detect_stencil_band_rows(bgr: np.ndarray, min_span_frac: float = 0.08) -> dict[str, int]:
    """Multi-colour DSV band rows (bust / underbust / waist / hip / hip2)."""
    import charuco_dsv_lib as clib

    return clib.detect_stencil_measurement_lines(bgr, min_span_frac=min_span_frac)


def init_level_ys_from_bands(views: dict[str, ViewData]) -> dict[str, dict[str, int]]:
    """Place girth rows from coloured stencil bands; propagate to side/back via pose."""
    out: dict[str, dict[str, int]] = {}
    front = views.get("front")
    band_rows: dict[str, int] = {}
    if front:
        band_rows = detect_stencil_band_rows(front.bgr)
        out["front"] = {lv: default_level_y(front, lv) for lv in LEVELS}
        for lv in ("bust", "underbust", "waist", "hip", "hem"):
            if lv == "hem" and "hip2" in band_rows:
                out["front"]["hem"] = band_rows["hip2"]
            elif lv in band_rows:
                out["front"][lv] = band_rows[lv]

    if front and front.pose and band_rows:
        ref_lv = next((lv for lv in ("waist", "bust", "hip") if lv in band_rows), None)
        if ref_lv:
            ref_y = out["front"][ref_lv]
            ref_frac = _torso_frac(front.pose, ref_y)
            for vname, vd in views.items():
                if vname == "front" or not vd.pose:
                    continue
                out.setdefault(vname, {lv: default_level_y(vd, lv) for lv in LEVELS})
                side_bands = detect_stencil_band_rows(vd.bgr)
                for lv in ("bust", "underbust", "waist", "hip"):
                    if lv in side_bands:
                        out[vname][lv] = side_bands[lv]
                    elif lv in out.get("front", {}):
                        out[vname][lv] = _y_from_torso_frac(vd.pose, ref_frac + (
                            _torso_frac(front.pose, out["front"][lv]) - ref_frac
                        ))
    else:
        for vname, vd in views.items():
            out.setdefault(vname, {lv: default_level_y(vd, lv) for lv in LEVELS})
    return out


def _rectified_vest_mask(rectified_bgr: np.ndarray) -> np.ndarray:
    """Foreground mask on a flattened panel (vest + body, not white fill)."""
    hsv = cv2.cvtColor(rectified_bgr, cv2.COLOR_BGR2HSV)
    mask = ((hsv[:, :, 1] > 18) | (hsv[:, :, 2] < 248)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    return mask


def _native_row_to_rectified_y(
    y_native: int,
    center_x_native: float,
    cal: Any,
    panel_bounds_mm: tuple[float, float, float, float],
    px_per_mm: float,
) -> int:
    """Map a horizontal row in the original photo to rectified canvas Y."""
    pt_mm = cal.px_to_mm(
        np.array([[center_x_native, float(y_native)]], dtype=np.float64)
    )[0]
    _x0, y0, _x1, _y1 = panel_bounds_mm
    return int(round((float(pt_mm[1]) - y0) * px_per_mm))


def _width_cm_rectified_row(mask: np.ndarray, y: int, cm_per_px: float, pose: dict | None = None) -> float | None:
    """Central torso run on a rectified row (pose ignored — native coords invalid here)."""
    h, w = mask.shape
    y = int(np.clip(y, 0, h - 1))
    row = mask[y]
    # search central 55% of canvas only (drops panel wings)
    x_margin = int(w * 0.225)
    seg = row[x_margin : w - x_margin]
    xs = np.where(seg > 128)[0]
    if len(xs) < 2:
        return None
    splits = np.where(np.diff(xs) > 2)[0]
    groups = np.split(xs, splits + 1)
    best = max(groups, key=len)
    if len(best) < 2:
        return None
    width_px = best[-1] - best[0]
    return round(width_px * cm_per_px, 2)


def measure_rectified_front_widths(
    front_bgr: np.ndarray,
    slot_name: str = "F1",
    panel_margin_mm: float = 220.0,
    stencil_spec_path: Path | None = None,
    pose: dict | None = None,
) -> tuple[Any, dict[str, float], dict[str, int]]:
    """
    Flatten the front panel via ChArUco and measure vest width at band rows.

    Band rows are detected on the native photo, then mapped into rectified Y
    via the ChArUco homography so bust / waist / hip align correctly.

    Returns ``(rectified_view, widths_cm, band_rows_rect_px)``.
    """
    import charuco_dsv_lib as clib

    spec = clib.CharucoRectifySpec(px_per_mm=3.0, margin_mm=40.0)
    slots = clib.default_dsv_marker_slots(stencil_spec_path)
    slot = slots[slot_name]
    cal, center_px, _ = clib.find_charuco_slot_in_image(front_bgr, slot, spec=spec)
    if cal.H_px_to_mm is None or cal.charuco_corners < 4:
        raise ValueError(f"{slot_name}: need >=4 ChArUco corners for rectified measure")

    slot.center_px = center_px
    pt_mm = cal.px_to_mm(np.array([[center_px[0], center_px[1]]], dtype=np.float64))[0]
    slot.center_x_mm = float(pt_mm[0])
    slot.center_y_mm = float(pt_mm[1])

    bounds = clib._board_extent_mm(slot, panel_margin_mm)
    flat = clib.rectify_image_by_charuco(front_bgr, cal, slot, spec, panel_mm_bounds=bounds)
    native_bands = detect_stencil_band_rows(front_bgr, min_span_frac=0.08)
    mask = _rectified_vest_mask(flat.image_bgr)
    cm_per_px = flat.mm_per_px_out / 10.0

    band_rows_rect: dict[str, int] = {}
    widths: dict[str, float] = {}
    for lv, y_nat in native_bands.items():
        key = "hem" if lv == "hip2" else lv
        if key not in _GIRTH_LEVELS and key != "hem":
            continue
        y_rect = _native_row_to_rectified_y(
            y_nat, center_px[0], cal, bounds, spec.px_per_mm
        )
        band_rows_rect[key] = y_rect
        w = _width_cm_rectified_row(mask, y_rect, cm_per_px, pose)
        if w:
            widths[key] = w
    return flat, widths, band_rows_rect


def run_charuco_rectified_measurement(
    paths: dict[str, str | Path],
    height_cm: float = 170.0,
    body_profile: BodyProfile | None = None,
    tape_cm: dict[str, float] | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """
    One-shot measurement using ChArUco scale + rectified front widths.

    * Front width: flattened panel via F1 (fallback F0)
    * Side depth: native side mask at band-synced rows
    * Scale: ChArUco on front/back when decodable, else stature
    """
    import charuco_dsv_lib as clib

    profile = body_profile or BodyProfile(sex="male", build="average", clothing="dsv_vest")
    out_dir = out_dir or (ROOT / "assets/dsv_charuco/rectified")
    out_dir.mkdir(parents=True, exist_ok=True)

    views: dict[str, ViewData] = {}
    for name, path in paths.items():
        vd = analyze_view(name, path)
        vd.bgr = orient_view_bgr(name, vd.bgr)
        ml = _import_markerless()
        mask_raw, pose, warn = ml.analyze_view(vd.bgr)
        vd.mask_raw = mask_raw
        vd.mask = refine_body_mask(mask_raw, pose, name)
        vd.pose = pose
        vd.top_px, vd.bottom_px = _vertical_extent(mask_raw)
        if warn:
            vd.warnings.append(warn)
        slot = _CHARUCO_SLOT_BY_VIEW.get(name)
        if slot and not calibrate_scale_charuco(vd, slot):
            calibrate_scale(vd, height_cm=height_cm)
        elif not slot:
            calibrate_scale(vd, height_cm=height_cm)
        views[name] = vd

    flat = None
    rect_widths: dict[str, float] = {}
    rect_bands: dict[str, int] = {}
    band_widths: dict[str, float] = {}
    band_width_detail: dict[str, Any] = {}
    front_slot = "F1"
    front = views.get("front")
    front_cal = getattr(front, "charuco_cal", None) if front else None
    if front:
        for try_slot in ("F1", "F0"):
            try:
                flat, rect_widths, rect_bands = measure_rectified_front_widths(
                    front.bgr, try_slot, pose=front.pose
                )
                front_slot = try_slot
                if flat.calibration.mm_per_px:
                    front.cm_per_px = flat.calibration.mm_per_px / 10.0
                    front.scale_method = f"charuco_{try_slot}_rectified"
                    front_cal = flat.calibration
                cv2.imwrite(
                    str(out_dir / f"front_{try_slot}_flat.png"),
                    flat.image_bgr,
                    [cv2.IMWRITE_PNG_COMPRESSION, 1],
                )
                break
            except ValueError:
                continue

        native_bands = detect_stencil_band_rows(front.bgr, min_span_frac=0.08)
        band_hits = clib.measure_front_widths_from_bands(
            front.bgr,
            band_rows=native_bands,
            body_mask=front.mask,
            mm_per_px=front_cal.mm_per_px if front_cal else None,
            calibration=front_cal,
        )
        for lv, hit in band_hits.items():
            key = "hem" if lv == "hip2" else lv
            if key not in _GIRTH_LEVELS and key != "hem":
                continue
            ref_w = rect_widths.get(key)
            if ref_w and hit.width_cm < 0.45 * ref_w:
                hit.warnings.append(f"rejected:narrow_vs_rectified({hit.width_cm:.1f}<{ref_w:.1f}cm)")
                band_width_detail[key] = {
                    "level": lv,
                    "y_px": hit.y_px,
                    "width_cm": hit.width_cm,
                    "width_in": hit.width_in,
                    "rejected": True,
                    "warnings": hit.warnings,
                }
                continue
            band_widths[key] = hit.width_cm
            band_width_detail[key] = {
                    "level": lv,
                    "y_px": hit.y_px,
                    "width_cm": hit.width_cm,
                    "width_in": hit.width_in,
                    "left_x": hit.left_x,
                    "right_x": hit.right_x,
                    "px_per_eighth_in": hit.px_per_eighth_in,
                    "scale_source": hit.scale_source,
                    "edge_source": hit.edge_source,
                    "warnings": hit.warnings,
                }

    # One ChArUco scale for all views (height is NOT used for px scale when markers decode)
    charuco_cpp = [
        v.cm_per_px for v in views.values() if v.scale_method.startswith("charuco")
    ]
    if charuco_cpp:
        scale = float(np.median(charuco_cpp))
        for v in views.values():
            v.cm_per_px = scale
            v.scale_method = v.scale_method.replace("height_stature", "charuco_unified")
            if "charuco_unified" not in v.scale_method:
                v.scale_method = f"charuco_unified({v.scale_method})"

    unify_scales(views)
    level_ys = init_level_ys_from_bands(views)
    if rect_bands and front:
        for lv, y in rect_bands.items():
            key = "hem" if lv == "hip2" else lv
            if key in LEVELS:
                level_ys.setdefault("front", {})[key] = y

    measures = compute_measurements(
        views, level_ys, body_profile=profile, height_cm=height_cm,
    )

    # Prefer coloured-band widths; fall back to rectified mask widths
    width_by_level = {**rect_widths, **band_widths}
    final: list[LineMeasure] = []
    for m in measures:
        if m.level in width_by_level and m.level in _GIRTH_LEVELS:
            w = width_by_level[m.level]
            d = m.depth_cm
            if m.level in band_widths:
                src_kind = "band_tape"
            else:
                src_kind = f"charuco_rectified_{front_slot}"
            if d:
                g = ellipse_girth(w, d)
                src = f"{src_kind}+side"
            else:
                g = ellipse_girth(w, 0.68 * w) if w else None
                src = src_kind
            final.append(
                LineMeasure(
                    level=m.level,
                    y_front=m.y_front,
                    y_side=m.y_side,
                    y_back=m.y_back,
                    width_cm=w,
                    depth_cm=d,
                    girth_cm=g,
                    source=src,
                )
            )
        else:
            final.append(m)

    if tape_cm:
        final = apply_tape_calibration(final, tape_cm)

    summary: dict[str, Any] = {
        "method": "charuco_rectified",
        "front_slot": front_slot,
        "scales": {k: {"cm_per_px": v.cm_per_px, "method": v.scale_method} for k, v in views.items()},
        "rectified_widths_cm": rect_widths,
        "band_widths_cm": band_widths,
        "band_width_detail": band_width_detail,
        "rectified_band_rows": rect_bands,
        "level_ys": level_ys,
        "measures": [
            {
                "level": m.level,
                "width_cm": m.width_cm,
                "depth_cm": m.depth_cm,
                "girth_cm": m.girth_cm,
                "source": m.source,
            }
            for m in final
        ],
        "girths_cm": {m.level: m.girth_cm for m in final if m.girth_cm and m.level in _GIRTH_LEVELS},
        "outputs": {"rectified_png": str(out_dir / f"front_{front_slot}_flat.png")} if flat else {},
        "warnings": [w for v in views.values() for w in v.warnings],
    }
    save_session(out_dir / "measurement_result.json", summary)
    return summary


def compare_body_profiles(
    paths: dict[str, str | Path],
    height_cm: float,
    profiles: list[BodyProfile],
    weight_kg: float | None = None,
    tape_cm: dict[str, float] | None = None,
    ref_kind: str | None = None,
) -> list[dict[str, Any]]:
    """Load once, run girths for each BodyProfile — for notebook A/B tests."""
    views: dict[str, ViewData] = {}
    for name, path in paths.items():
        vd = analyze_view(name, path)
        calibrate_scale(vd, height_cm=height_cm, ref_kind=ref_kind)
        views[name] = vd

    rows: list[dict[str, Any]] = []
    for prof in profiles:
        ys = sync_girth_level_ys(
            views, init_level_ys(views), prof, height_cm, weight_kg,
        )
        ms = compute_measurements(
            views, ys,
            body_profile=prof,
            height_cm=height_cm,
            weight_kg=weight_kg,
            tape_cm=tape_cm,
        )
        bp = body_profile_summary(prof, views, height_cm, weight_kg)
        girths = {m.level: m.girth_cm for m in ms if m.girth_cm and m.level in _GIRTH_LEVELS}
        src = next((m.source for m in ms if m.level == "bust"), "")
        row: dict[str, Any] = {
            "sex": prof.sex,
            "build": prof.build,
            "clothing_cfg": prof.clothing,
            "clothing_detected": bp["clothing_detected"],
            "source": src,
            **{f"g_{k}": v for k, v in girths.items()},
        }
        if tape_cm:
            for k, tape in tape_cm.items():
                if k in girths:
                    row[f"err_{k}"] = round(girths[k] - tape, 1)
        rows.append(row)
    return rows


def body_profile_summary(
    profile: BodyProfile,
    views: dict[str, ViewData],
    height_cm: float | None = None,
    weight_kg: float | None = None,
) -> dict[str, Any]:
    """Diagnostics for notebook display."""
    front = views.get("front")
    if not front:
        return {"profile": profile.__dict__}
    from pipeline.measure.slice_measure import scan_torso_slices

    ml = _import_markerless()
    fmask = _meas_mask(front)
    fcx = int(np.median(np.where(fmask.any(axis=0))[0])) if fmask.any() else fmask.shape[1] // 2
    side = views.get("side")
    side_cpp = getattr(side, "cm_per_px_depth", side.cm_per_px if side else None) if side else None
    side_pv = None
    if side and side.pose:
        side_pv = ml._ProfileView(
            "side", _meas_mask(side), side.pose, side.top_px, side.bottom_px, side_cpp,
        )
    samples, _ = scan_torso_slices(
        fmask, front.pose, fcx, front.cm_per_px, side_pv, side_cpp,
    )
    hints = _capture_hints(views)
    clothing = detect_clothing(profile, hints, samples)
    notes = profile_notes(profile, clothing, height_cm, weight_kg)
    bmi = profile.bmi(height_cm, weight_kg)
    if bmi and profile.build == "average":
        if bmi < 19:
            notes.append("build_hint:slim")
        elif bmi > 26:
            notes.append("build_hint:curvy")
    return {
        "sex": profile.sex,
        "build": profile.build,
        "clothing_config": profile.clothing,
        "clothing_detected": clothing,
        "bmi": bmi,
        "torso_fracs": torso_fracs(profile),
        "notes": notes,
    }


def _draw_line_bold(
    out: np.ndarray,
    pt1: tuple[int, int],
    pt2: tuple[int, int],
    color: tuple[int, int, int],
    thick: int = _LINE_THICK,
) -> None:
    cv2.line(out, pt1, pt2, _OUTLINE_BGR, thick + 3, cv2.LINE_AA)
    cv2.line(out, pt1, pt2, color, thick, cv2.LINE_AA)


def _draw_label_bold(out: np.ndarray, text: str, org: tuple[int, int], color: tuple[int, int, int]) -> None:
    cv2.putText(out, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.62, _OUTLINE_BGR, 4, cv2.LINE_AA)
    cv2.putText(out, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.62, color, 2, cv2.LINE_AA)


def _torso_line_span(pose: dict | None, y: int, w: int) -> tuple[int, int]:
    if not pose:
        return 0, w
    ml = _import_markerless()
    bounds = ml._torso_x_bounds(pose, y, margin=1.12)
    if not bounds:
        return 0, w
    return max(0, bounds[0]), min(w, bounds[1])


def _draw_shoulder_traps(
    out: np.ndarray,
    shoulder: ShoulderMeasure | None,
) -> None:
    """Trapezius lines neck → each shoulder + shoulder width span."""
    if not shoulder:
        return
    neck = tuple(int(round(v)) for v in shoulder.neck_px)
    l_sh = tuple(int(round(v)) for v in shoulder.l_shoulder_px)
    r_sh = tuple(int(round(v)) for v in shoulder.r_shoulder_px)
    trap_color = (0, 160, 255)
    width_color = (0, 140, 255)
    for c, r in ((neck, 7), (l_sh, 6), (r_sh, 6)):
        cv2.circle(out, c, r + 2, _OUTLINE_BGR, -1)
        cv2.circle(out, c, r, trap_color if c != neck else (0, 120, 220), -1)
    _draw_line_bold(out, neck, l_sh, trap_color, _TRAP_THICK)
    _draw_line_bold(out, neck, r_sh, trap_color, _TRAP_THICK)
    if shoulder.shoulder_width_cm is not None:
        _draw_line_bold(out, l_sh, r_sh, width_color, _SHOULDER_WIDTH_THICK)
        mid = ((l_sh[0] + r_sh[0]) // 2, (l_sh[1] + r_sh[1]) // 2 - 14)
        _draw_label_bold(out, f"shoulder {shoulder.shoulder_width_cm:.1f}cm", mid, width_color)
    if shoulder.trap_left_cm is not None:
        _draw_label_bold(out, f"trap L {shoulder.trap_left_cm:.1f}", (l_sh[0] - 8, l_sh[1] - 12), trap_color)
    if shoulder.trap_right_cm is not None:
        _draw_label_bold(out, f"trap R {shoulder.trap_right_cm:.1f}", (r_sh[0] - 8, r_sh[1] - 12), trap_color)


def draw_overlay(
    bgr: np.ndarray,
    mask: np.ndarray,
    level_ys: dict[str, int],
    measures: dict[str, LineMeasure],
    view_name: str,
    shoulder: ShoulderMeasure | None = None,
    pose: dict | None = None,
) -> np.ndarray:
    out = bgr.copy()
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        cnt = max(contours, key=cv2.contourArea)
        cv2.drawContours(out, [cnt], -1, _OUTLINE_BGR, 5)
        cv2.drawContours(out, [cnt], -1, (40, 40, 40), 2)
    h, w = out.shape[:2]
    _draw_shoulder_traps(out, shoulder)
    for lv in LEVELS:
        y = level_ys.get(lv)
        if y is None:
            continue
        if lv in ("neck", "shoulder") and shoulder:
            if lv == "neck":
                nx = int(shoulder.neck_px[0])
                _draw_line_bold(out, (nx - 40, y), (nx + 40, y), LEVEL_COLORS_BGR[lv], 3)
            continue
        color = LEVEL_COLORS_BGR[lv]
        x1, x2 = _torso_line_span(pose, y, w)
        _draw_line_bold(out, (x1, y), (x2, y), color, _LINE_THICK)
        m = measures.get(lv)
        label = lv
        if m:
            if view_name == "front" and m.width_cm:
                label = f"{lv}  {m.width_cm:.1f}cm"
            elif view_name == "side" and m.depth_cm:
                label = f"{lv}  {m.depth_cm:.1f}cm"
            elif m.girth_cm:
                label = f"{lv}  {m.girth_cm:.0f}cm"
        _draw_label_bold(out, label, (x1 + 4, max(22, y - 8)), color)
    return out


def compare_to_tape(
    measures: list[LineMeasure],
    tape_cm: dict[str, float],
) -> list[dict[str, Any]]:
    """Diff predicted girths vs tape-measured ground truth."""
    by_lv = {m.level: m for m in measures}
    rows: list[dict[str, Any]] = []
    for level, tape in tape_cm.items():
        m = by_lv.get(level)
        pred = m.girth_cm if m else None
        err = round(pred - tape, 1) if pred is not None else None
        rows.append(
            {
                "level": level,
                "tape_cm": tape,
                "tape_in": round(tape / 2.54, 1),
                "predicted_cm": pred,
                "error_cm": err,
                "error_in": round(err / 2.54, 1) if err is not None else None,
            }
        )
    return rows


def session_summary(
    views: dict[str, ViewData],
    measures: list[LineMeasure],
    shoulders: list[ShoulderMeasure] | None = None,
    tape_cm: dict[str, float] | None = None,
    body_profile: BodyProfile | None = None,
    height_cm: float | None = None,
    weight_kg: float | None = None,
) -> dict[str, Any]:
    sw = best_shoulder_width(shoulders or [])
    summary: dict[str, Any] = {
        "views": {
            k: {
                "path": str(v.path),
                "scale_method": v.scale_method,
                "cm_per_px": round(v.cm_per_px, 5),
                "magenta_rows": v.magenta_rows,
                "warnings": v.warnings,
            }
            for k, v in views.items()
        },
        "shoulder_width_cm": sw,
        "shoulder_width_in": round(sw / 2.54, 1) if sw else None,
        "shoulders": [
            {
                "view": s.view,
                "shoulder_width_cm": s.shoulder_width_cm,
                "shoulder_width_in": round(s.shoulder_width_cm / 2.54, 1)
                if s.shoulder_width_cm
                else None,
                "trap_left_cm": s.trap_left_cm,
                "trap_right_cm": s.trap_right_cm,
                "slope_deg_left": s.shoulder_slope_deg_l,
                "slope_deg_right": s.shoulder_slope_deg_r,
            }
            for s in (shoulders or [])
        ],
        "levels": [
            {
                "level": m.level,
                "y_front": m.y_front,
                "y_side": m.y_side,
                "y_back": m.y_back,
                "width_cm": m.width_cm,
                "depth_cm": m.depth_cm,
                "girth_cm": m.girth_cm,
                "girth_in": round(m.girth_cm / 2.54, 1) if m.girth_cm else None,
                "source": m.source,
            }
            for m in measures
        ],
    }
    if body_profile:
        summary["body_profile"] = body_profile_summary(
            body_profile, views, height_cm, weight_kg,
        )
    if tape_cm:
        summary["tape_cm"] = tape_cm
        summary["tape_validation"] = compare_to_tape(measures, tape_cm)
    return summary


def save_session(path: str | Path, payload: dict[str, Any]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2))
    return p
