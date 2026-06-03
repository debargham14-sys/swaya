"""
Swaya QC engine - orchestrator.

Runs the full quality-check pipeline on a flat-lay photo of a finished blouse
inside the standardized QC framework, comparing it against the order spec.

  Stage 1  ChArUco/ArUco detection + px<->mm calibration   (charuco.py)
  Stage 2  framework inner boundary = measurement zone      (framework.py)
  Stage 3  blouse silhouette extraction                     (silhouette.py)
  Stage 4  direct dimensional measurement                   (landmarks.py + dimensions.py)
  Stage 5  comparison against spec (tolerance tiers)         (compare.py)
  Stage 6  symmetry analysis                                 (symmetry.py)
  Stage 7  checklist (47 checks; features scaffolded)        (checklist.py)
  Stage 8  QC report + annotated photo                       (report.py)

CLI:
  python -m pipeline.qc.qc_engine --photo qc.jpg --order-id SW-2026-04827
  python -m pipeline.qc.qc_engine --photo qc.jpg --spec order.json --debug-dir out/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.qc import charuco, framework, silhouette as sil_mod
from pipeline.qc.compare import NEEDS_REVIEW, compare_dimensions
from pipeline.qc.dimensions import measure_dimensions
from pipeline.qc.framework_spec import STANDARD_A1, FrameworkSpec
from pipeline.qc.landmarks import extract_landmarks
from pipeline.qc.report import (
    QCResult,
    build_checks,
    overall_verdict,
    render_annotated,
)
from pipeline.qc.spec import OrderSpec, load_spec
from pipeline.qc.symmetry import analyze_symmetry


def run_qc(
    photo: str | Path,
    spec: OrderSpec,
    framework_spec: FrameworkSpec = STANDARD_A1,
    debug_dir: Path | None = None,
) -> QCResult:
    img = cv2.imread(str(photo), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"unreadable photo: {photo}")

    warnings: list[str] = []

    # Stage 1
    calib = charuco.calibrate(img, framework_spec)
    warnings.extend(calib.warnings)
    if calib.needs_retake:
        checks = build_checks([], None, spec)
        for c in checks:
            c.status = NEEDS_REVIEW if c.status == "pass" else c.status
        return QCResult(
            order_id=spec.order_id, tier=spec.tier, variant=spec.variant,
            overall_status=NEEDS_REVIEW, score=0.0, checks=checks,
            calibration=calib.to_dict(),
            warnings=warnings + ["needs_retake: fewer than 3 framework fiducials detected"],
        )

    # Stage 2
    zone = framework.detect_measurement_zone(img.shape, calib, framework_spec)
    if not framework.corners_visible(calib, img.shape, framework_spec):
        warnings.append("not_all_fiducials_inside_frame")

    # Stage 3
    sil = sil_mod.extract_silhouette(img, zone)
    warnings.extend(sil.warnings)

    comparisons = []
    symmetry = None
    dims_dict: dict = {}

    if sil.area_px > 0:
        # Stage 4
        lm = extract_landmarks(sil.mask, calib, framework_spec)
        if lm is None:
            warnings.append("landmark_extraction_failed")
        else:
            dims = measure_dimensions(lm)
            warnings.extend(dims.warnings)
            dims_dict = dims.to_dict()
            # Stage 5
            comparisons = compare_dimensions(dims, spec)
            # Stage 6
            symmetry = analyze_symmetry(lm)
            warnings.extend(symmetry.warnings)
    else:
        warnings.append("no_silhouette_dimensions_skipped")

    # Stage 7 + 8
    checks = build_checks(comparisons, symmetry, spec)
    overall_status, score = overall_verdict(checks)

    annotated_path: str | None = None
    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        annotated = render_annotated(img, calib, zone, symmetry, comparisons, overall_status, score)
        annotated_path = str(debug_dir / "qc_annotated.jpg")
        cv2.imwrite(annotated_path, annotated)
        if sil.mask is not None:
            cv2.imwrite(str(debug_dir / "qc_silhouette.png"), sil.mask)

    return QCResult(
        order_id=spec.order_id,
        tier=spec.tier,
        variant=spec.variant,
        overall_status=overall_status,
        score=score,
        checks=checks,
        calibration=calib.to_dict(),
        dimensions=dims_dict,
        comparisons=[c.to_dict() for c in comparisons],
        symmetry=symmetry.to_dict() if symmetry else {},
        annotated_path=annotated_path,
        warnings=warnings,
    )


def print_result(r: QCResult) -> None:
    print(f"\n{'#' * 60}")
    print("  SWAYA QC ENGINE")
    print(f"{'#' * 60}")
    print(f"  Order {r.order_id} | tier={r.tier} | variant={r.variant}")
    print(f"  Calibration: {r.calibration.get('method')} "
          f"({r.calibration.get('corners_found')}/4 fiducials)")
    print(f"  VERDICT: {r.overall_status.upper()}  score={r.score * 100:.0f}%")
    if r.comparisons:
        print(f"  {'dimension':18}{'meas':>8}{'target':>8}{'dev':>7}{'tol':>6}  status")
        for c in r.comparisons:
            meas = f"{c['measured_mm']:.0f}" if c['measured_mm'] is not None else "--"
            dev = f"{c['deviation_mm']:+.0f}" if c['deviation_mm'] is not None else "--"
            print(f"  {c['name']:18}{meas:>8}{c['target_mm']:>8.0f}{dev:>7}"
                  f"{c['tolerance_mm']:>6.0f}  {c['status']}")
    if r.symmetry:
        print(f"  Symmetry: max_dev={r.symmetry['max_deviation_mm']}mm "
              f"iou={r.symmetry['iou']}")
    print("  Category summary:")
    for cat, s in r.category_summary().items():
        print(f"    {cat:34} {s}")
    if r.warnings:
        print("  notes: " + "; ".join(r.warnings[:8]))
    print(f"{'#' * 60}")


def main() -> None:
    p = argparse.ArgumentParser(description="Swaya QC engine")
    p.add_argument("--photo", type=Path, required=True, help="flat-lay blouse-on-framework photo")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--spec", type=Path, help="order spec JSON file")
    g.add_argument("--order-id", type=str, help="order id resolved via OrderRepository")
    p.add_argument("--debug-dir", type=Path, default=None)
    args = p.parse_args()

    if args.spec:
        spec = load_spec(spec_json=args.spec.read_text())
    else:
        spec = load_spec(order_id=args.order_id)

    r = run_qc(args.photo, spec, debug_dir=args.debug_dir)
    print_result(r)
    if args.debug_dir:
        (args.debug_dir / "qc_result.json").write_text(json.dumps(r.to_dict(), indent=2))
        print(f"\nSaved: {args.debug_dir / 'qc_result.json'}")
        if r.annotated_path:
            print(f"Annotated: {r.annotated_path}")


if __name__ == "__main__":
    main()
