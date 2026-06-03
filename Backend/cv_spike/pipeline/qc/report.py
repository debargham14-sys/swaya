"""
Stage 8 - QC report assembly + annotated photo.

Combines every stage into a single QCResult: per-check status across the full
47-check schema, an overall Pass / Fail / NeedsReview verdict with a confidence
score, and an annotated photo that draws the measurement zone, symmetry axis,
and a pass/fail summary panel.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from pipeline.qc.charuco import Calibration
from pipeline.qc.checklist import CHECKLIST, HANGING, HUMAN, PHOTO, _SILHOUETTE_PROXY
from pipeline.qc.compare import DimComparison
from pipeline.qc.framework import MeasurementZone
from pipeline.qc.spec import OrderSpec
from pipeline.qc.symmetry import SymmetryResult

PASS = "pass"
FAIL = "fail"
NEEDS_REVIEW = "needs_review"
SKIPPED = "skipped"

_COLOR = {
    PASS: (60, 170, 60),
    FAIL: (40, 40, 220),
    NEEDS_REVIEW: (40, 160, 220),
    SKIPPED: (140, 140, 140),
}


@dataclass
class QCCheck:
    id: str
    category: int
    category_name: str
    label: str
    method: str
    status: str
    confidence: float = 0.0
    measured_mm: float | None = None
    target_mm: float | None = None
    deviation_mm: float | None = None
    tolerance_mm: float | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "category_name": self.category_name,
            "label": self.label,
            "method": self.method,
            "status": self.status,
            "confidence": round(self.confidence, 2),
            "measured_mm": round(self.measured_mm, 1) if self.measured_mm is not None else None,
            "target_mm": round(self.target_mm, 1) if self.target_mm is not None else None,
            "deviation_mm": round(self.deviation_mm, 1) if self.deviation_mm is not None else None,
            "tolerance_mm": self.tolerance_mm,
            "note": self.note,
        }


@dataclass
class QCResult:
    order_id: str
    tier: str
    variant: str
    overall_status: str
    score: float
    checks: list[QCCheck] = field(default_factory=list)
    calibration: dict = field(default_factory=dict)
    dimensions: dict = field(default_factory=dict)
    comparisons: list[dict] = field(default_factory=list)
    symmetry: dict = field(default_factory=dict)
    annotated_path: str | None = None
    warnings: list[str] = field(default_factory=list)

    def category_summary(self) -> dict:
        summary: dict[str, dict] = {}
        for c in self.checks:
            key = f"{c.category}:{c.category_name}"
            s = summary.setdefault(key, {PASS: 0, FAIL: 0, NEEDS_REVIEW: 0, SKIPPED: 0})
            s[c.status] = s.get(c.status, 0) + 1
        return summary

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "tier": self.tier,
            "variant": self.variant,
            "overall_status": self.overall_status,
            "score": round(self.score, 3),
            "calibration": self.calibration,
            "dimensions": self.dimensions,
            "comparisons": self.comparisons,
            "symmetry": self.symmetry,
            "category_summary": self.category_summary(),
            "checks": [c.to_dict() for c in self.checks],
            "annotated_path": self.annotated_path,
            "warnings": self.warnings,
        }


def build_checks(
    comparisons: list[DimComparison],
    symmetry: SymmetryResult | None,
    spec: OrderSpec,
) -> list[QCCheck]:
    comp_by = {c.name: c for c in comparisons}
    sym_by = {s.name: s for s in (symmetry.sub_checks if symmetry else [])}
    feature_ids = {str(f.get("id") or f.get("type", "")).lower() for f in spec.features}

    checks: list[QCCheck] = []
    for d in CHECKLIST:
        ck = QCCheck(
            id=d.id, category=d.category, category_name=d.category_name,
            label=d.label, method=d.method, status=NEEDS_REVIEW,
        )
        if d.category == 1:
            comp = comp_by.get(d.dimension or d.id)
            if comp is None:
                ck.status = SKIPPED
                ck.note = "not specified for this order"
            else:
                ck.status = comp.status
                ck.confidence = comp.confidence
                ck.measured_mm = comp.measured_mm
                ck.target_mm = comp.target_mm
                ck.deviation_mm = comp.deviation_mm
                ck.tolerance_mm = comp.tolerance_mm
        elif d.category == 2:
            sub = sym_by.get(d.id)
            if sub is not None:
                ck.status = sub.status
                ck.confidence = 0.7
                ck.deviation_mm = sub.deviation_mm
                ck.tolerance_mm = sub.tolerance_mm
            elif d.id in _SILHOUETTE_PROXY and "silhouette_symmetry" in sym_by:
                proxy = sym_by["silhouette_symmetry"]
                ck.status = proxy.status
                ck.confidence = 0.45
                ck.deviation_mm = proxy.deviation_mm
                ck.tolerance_mm = proxy.tolerance_mm
                ck.note = "approximated from silhouette mirror"
            else:
                ck.note = "finer detector pending"
        else:
            ck.status = NEEDS_REVIEW
            if d.method == HANGING:
                ck.note = "requires hanging photo"
            elif d.method == HUMAN:
                ck.note = "requires human inspection"
            elif d.category == 3 and d.id not in feature_ids and not feature_ids:
                ck.note = "feature detector pending"
            else:
                ck.note = "feature detector pending"
        checks.append(ck)
    return checks


def overall_verdict(checks: list[QCCheck]) -> tuple[str, float]:
    photo = [c for c in checks if c.method == PHOTO]
    decided = [c for c in photo if c.status in (PASS, FAIL)]
    if any(c.status == FAIL for c in photo):
        status = FAIL
    elif any(c.status == NEEDS_REVIEW for c in photo):
        status = NEEDS_REVIEW
    else:
        status = PASS
    passed = sum(1 for c in decided if c.status == PASS)
    score = passed / len(decided) if decided else 0.0
    return status, score


def render_annotated(
    img_bgr: np.ndarray,
    calib: Calibration,
    zone: MeasurementZone | None,
    symmetry: SymmetryResult | None,
    comparisons: list[DimComparison],
    overall_status: str,
    score: float,
) -> np.ndarray:
    ov = img_bgr.copy()

    if zone is not None:
        cv2.polylines(ov, [zone.corners_px.round().astype(np.int32)], True, (60, 170, 60), 2)

    if symmetry is not None and calib.H_mm_to_px is not None:
        pts_mm = np.array([[symmetry.axis_x_mm, 0.0], [symmetry.axis_x_mm, 1e4]])
        try:
            pts_px = calib.mm_to_px(pts_mm).round().astype(int)
            cv2.line(ov, tuple(pts_px[0]), tuple(pts_px[1]), (200, 0, 200), 2)
        except Exception:  # noqa: BLE001
            pass

    # Summary panel
    panel_w = 360
    h = ov.shape[0]
    panel = np.full((h, panel_w, 3), 245, np.uint8)
    y = 36
    banner = _COLOR.get(overall_status, (120, 120, 120))
    cv2.rectangle(panel, (0, 0), (panel_w, 50), banner, -1)
    cv2.putText(panel, f"QC {overall_status.upper()}  {score * 100:.0f}%", (14, 33),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
    y = 80
    cv2.putText(panel, "DIMENSIONS (mm)", (14, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (40, 40, 40), 1)
    y += 26
    for c in comparisons:
        col = _COLOR.get(c.status, (120, 120, 120))
        meas = f"{c.measured_mm:.0f}" if c.measured_mm is not None else "--"
        dev = f"{c.deviation_mm:+.0f}" if c.deviation_mm is not None else "--"
        cv2.putText(panel, f"{c.name[:14]:14} {meas:>5}/{c.target_mm:.0f} ({dev})", (14, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.46, col, 1)
        y += 22
        if y > h - 30:
            break

    out = np.full((h, ov.shape[1] + panel_w, 3), 255, np.uint8)
    out[:, : ov.shape[1]] = ov
    out[:, ov.shape[1]:] = panel
    return out
