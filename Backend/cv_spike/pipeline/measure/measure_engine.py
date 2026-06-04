"""
Unified body-measurement engine for Swaya.

Chooses the best available method and returns one consistent result:

  Priority:
    1. mesh   -- 3D body mesh (SMPL via 4D-Humans, or a supplied .obj) ->
                 cross-section girths (most accurate, ties to the try-on avatar)
    2. photo  -- silhouette + MediaPipe pose ellipse estimator (markerless.py)

Inputs: front photo + optional side photo + height(cm) + weight(kg).
Output: girths in cm + inches, the backend used, and confidence/warnings.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.measure import markerless, mesh_measure, smpl_backend

CM_PER_IN = 2.54
TARGETS = ("bust", "underbust", "waist", "hip")
# Mesh girths below this for bust likely mean bad HMR2 fit (full-frame / loose clothes).
_MIN_PLAUSIBLE_BUST_CM = 60.0


def _mesh_girths_plausible(girths: dict[str, float]) -> bool:
    bust = girths.get("bust")
    return bust is not None and bust >= _MIN_PLAUSIBLE_BUST_CM


@dataclass
class EngineResult:
    backend: str
    height_cm: float
    weight_kg: float
    bmi: float
    girths_cm: dict[str, float] = field(default_factory=dict)
    girths_raw_cm: dict[str, float] = field(default_factory=dict)
    calibration_profile: str | None = None
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def girths_in(self) -> dict[str, float]:
        return {k: round(v / CM_PER_IN, 1) for k, v in self.girths_cm.items()}

    def to_dict(self) -> dict:
        return {
            "backend": self.backend,
            "height_cm": self.height_cm,
            "weight_kg": self.weight_kg,
            "bmi": self.bmi,
            "confidence": self.confidence,
            "girths_cm": self.girths_cm,
            "girths_raw_cm": self.girths_raw_cm or None,
            "girths_in": self.girths_in(),
            "calibration_profile": self.calibration_profile,
            "warnings": self.warnings,
        }


def _from_mesh_measurement(mm: mesh_measure.MeshMeasurement, backend: str, weight_kg: float) -> EngineResult:
    bmi = weight_kg / (mm.height_cm / 100.0) ** 2
    return EngineResult(
        backend=f"mesh:{backend}",
        height_cm=mm.height_cm,
        weight_kg=weight_kg,
        bmi=round(bmi, 1),
        girths_cm=dict(mm.girths_cm),
        confidence=0.85 if backend != "obj" else 0.9,
        warnings=list(mm.warnings),
    )


def _from_markerless(mk: "markerless.MarkerlessResult", weight_kg: float) -> EngineResult:
    girths = {
        lv.name: lv.girth_cm
        for lv in mk.levels
        if lv.name in TARGETS and lv.girth_cm is not None
    }
    conf = max((lv.confidence for lv in mk.levels), default=0.3)
    return EngineResult(
        backend="photo:body-slice",
        height_cm=mk.height_cm,
        weight_kg=weight_kg,
        bmi=mk.bmi,
        girths_cm=girths,
        girths_raw_cm=dict(girths),
        confidence=conf,
        warnings=list(mk.warnings) + ["approximate: fitted clothing improves accuracy"],
    )


def _apply_calibration(result: EngineResult, tape_in: str | None, tape_cm: str | None,
                       calibration_path: Path | None) -> EngineResult:
    from pipeline.measure.calibration import apply_girth_calibration, fit_profile, load_profile, parse_tape_spec

    raw = dict(result.girths_cm)
    if not raw:
        return result
    result.girths_raw_cm = raw
    if calibration_path:
        prof = load_profile(calibration_path)
        result.girths_cm = apply_girth_calibration(raw, prof)
        result.calibration_profile = prof.name
        result.warnings.append(f"calibrated:{prof.name}")
    elif tape_in or tape_cm:
        anchors = parse_tape_spec(tape_cm or tape_in, unit="cm" if tape_cm else "in")
        prof = fit_profile(anchors, raw, name="inline_tape")
        result.girths_cm = apply_girth_calibration(raw, prof)
        result.calibration_profile = prof.name
        result.warnings.append("calibrated:inline_tape")
    return result


def _derive_height_from_ref(
    front: str | Path,
    ref_kind: str,
    ref_marker_mm: float,
) -> float | None:
    """Infer stature (cm) from ArUco/card scale × silhouette height in the front photo."""
    from pipeline.measure.markerless import analyze_view, _vertical_extent
    from pipeline.measure.scale_reference import detect_scale

    img = cv2.imread(str(front), cv2.IMREAD_COLOR)
    if img is None:
        return None
    sr = detect_scale(img, ref_kind, ref_marker_mm)
    if not sr.cm_per_px:
        return None
    mask, _, _ = analyze_view(img)
    top, bottom = _vertical_extent(mask)
    return sr.cm_per_px * max(1, bottom - top)


def _mesh_prefer(prefer: str) -> str:
    if prefer in ("obj", "four_d_humans", "smplx"):
        return prefer
    return "auto"


def measure(
    height_cm: float | None,
    weight_kg: float | None,
    front: str | Path | None = None,
    side: str | Path | None = None,
    back: str | Path | None = None,
    mesh_path: str | Path | None = None,
    prefer: str = "auto",
    debug_dir: Path | None = None,
    ref_kind: str | None = None,
    ref_marker_mm: float = 50.0,
    tape_in: str | None = None,
    tape_cm: str | None = None,
    calibration_path: Path | None = None,
) -> EngineResult:
    # 1. Mesh path (4D-Humans / SMPL-X / .obj). Needs a stature: explicit height or
    # inferred from ArUco scale × front silhouette.
    front_img = cv2.imread(str(front), cv2.IMREAD_COLOR) if front else None
    stature_cm = height_cm
    if stature_cm is None and ref_kind and front:
        stature_cm = _derive_height_from_ref(front, ref_kind, ref_marker_mm)

    use_mesh = prefer != "photo" and stature_cm is not None and front_img is not None
    if use_mesh:
        try:
            mm, backend = smpl_backend.measure_from_image_or_mesh(
                stature_cm,
                image_bgr=front_img,
                mesh_path=mesh_path,
                prefer=_mesh_prefer(prefer),
            )
            out = _from_mesh_measurement(mm, backend, weight_kg or 0.0)
            if height_cm is None and ref_kind:
                out.height_cm = round(stature_cm, 1)
                out.warnings.append(f"height_inferred_from_{ref_kind}")
            if not _mesh_girths_plausible(out.girths_cm):
                out.warnings.append("mesh_girths_implausible_fallback_to_photo")
                raise smpl_backend.BackendUnavailable("mesh girths out of range")
            if tape_in or tape_cm or calibration_path:
                out = _apply_calibration(out, tape_in, tape_cm, calibration_path)
            return out
        except smpl_backend.BackendUnavailable:
            if prefer in ("four_d_humans", "smplx", "obj"):
                raise
            pass  # fall through to photo estimator

    # 2. Photo silhouette + pose fallback (supports reference-object scale)
    if not front:
        raise SystemExit("No front photo and no mesh: cannot measure.")
    mk = markerless.estimate(
        front, side, height_cm, weight_kg, debug_dir=debug_dir,
        ref_kind=ref_kind, ref_marker_mm=ref_marker_mm, back_path=back,
    )
    out = _from_markerless(mk, weight_kg or 0.0)
    if tape_in or tape_cm or calibration_path:
        out = _apply_calibration(out, tape_in, tape_cm, calibration_path)
    return out


def print_result(r: EngineResult) -> None:
    print(f"\n{'#' * 56}")
    print("  SWAYA MEASUREMENT ENGINE")
    print(f"{'#' * 56}")
    print(f"  Backend: {r.backend}   conf={r.confidence:.2f}")
    if r.calibration_profile:
        print(f"  Calibration: {r.calibration_profile}")
    print(f"  Height {r.height_cm:.0f} cm | Weight {r.weight_kg:.0f} kg | BMI {r.bmi}")
    inches = r.girths_in()
    if r.girths_raw_cm:
        print(f"  {'girth':10} {'raw cm':>8} {'cal cm':>8} {'inches':>9}")
        for k in TARGETS:
            if k in r.girths_cm:
                raw = r.girths_raw_cm.get(k)
                raw_s = f"{raw:8.1f}" if raw is not None else f"{'--':>8}"
                print(f"  {k:10} {raw_s} {r.girths_cm[k]:8.1f} {inches[k]:9.1f}")
    else:
        print(f"  {'girth':10} {'cm':>8} {'inches':>9}")
        for k in TARGETS:
            if k in r.girths_cm:
                print(f"  {k:10} {r.girths_cm[k]:8.1f} {inches[k]:9.1f}")
    if r.warnings:
        print("  notes: " + "; ".join(r.warnings[:6]))
    print(f"{'#' * 56}")


def main() -> None:
    p = argparse.ArgumentParser(description="Swaya unified body measurement")
    p.add_argument("--front", type=Path, default=None)
    p.add_argument("--side", type=Path, default=None)
    p.add_argument("--back", type=Path, default=None)
    p.add_argument("--mesh", type=Path, default=None, help="pre-exported body mesh (.obj/.ply)")
    p.add_argument("--height", type=float, default=None, help="height cm (or use --ref)")
    p.add_argument("--weight", type=float, default=None, help="weight kg (optional)")
    p.add_argument("--ref", choices=("aruco", "card", "a4"), default=None,
                   help="reference object in frame for scale instead of height")
    p.add_argument("--ref-mm", type=float, default=50.0, help="ArUco marker side length (mm)")
    p.add_argument("--prefer", choices=("auto", "obj", "four_d_humans", "smplx", "photo"), default="auto")
    p.add_argument("--tape-in", type=str, default=None, help="tape anchors in inches, e.g. bust=44,waist=38")
    p.add_argument("--tape-cm", type=str, default=None, help="tape anchors in cm")
    p.add_argument("--calibration", type=Path, default=None, help="saved calibration profile JSON")
    p.add_argument("--debug-dir", type=Path, default=None)
    args = p.parse_args()
    if args.height is None and args.ref is None:
        p.error("provide --height or --ref (aruco/card/a4)")
    prefer = "auto" if args.prefer == "photo" else args.prefer
    r = measure(
        args.height, args.weight, front=args.front, side=args.side, back=args.back,
        mesh_path=args.mesh, prefer=prefer, debug_dir=args.debug_dir,
        ref_kind=args.ref, ref_marker_mm=args.ref_mm,
        tape_in=args.tape_in, tape_cm=args.tape_cm, calibration_path=args.calibration,
    )
    print_result(r)
    if args.debug_dir:
        args.debug_dir.mkdir(parents=True, exist_ok=True)
        (args.debug_dir / "engine_result.json").write_text(json.dumps(r.to_dict(), indent=2))


if __name__ == "__main__":
    main()
