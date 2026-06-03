"""
Stage 5 (logic) - Compare measured dimensions against the order spec.

Each shared dimension yields a deviation in mm and a Pass / Fail / NeedsReview
status against the tier tolerance. Low-confidence or unmeasurable dimensions are
flagged NeedsReview rather than Fail.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.qc.dimensions import DimensionSet
from pipeline.qc.spec import OrderSpec, tolerance_mm

PASS = "pass"
FAIL = "fail"
NEEDS_REVIEW = "needs_review"

_MIN_CONFIDENCE = 0.3


@dataclass
class DimComparison:
    name: str
    measured_mm: float | None
    target_mm: float
    deviation_mm: float | None
    tolerance_mm: float
    status: str
    confidence: float

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "measured_mm": round(self.measured_mm, 1) if self.measured_mm is not None else None,
            "target_mm": round(self.target_mm, 1),
            "deviation_mm": round(self.deviation_mm, 1) if self.deviation_mm is not None else None,
            "tolerance_mm": self.tolerance_mm,
            "status": self.status,
            "confidence": round(self.confidence, 2),
        }


def compare_dimensions(dims: DimensionSet, spec: OrderSpec) -> list[DimComparison]:
    out: list[DimComparison] = []
    for name, target in spec.target_dims_mm.items():
        tol = tolerance_mm(name, spec.tier)
        m = dims.measurements.get(name)
        if m is None or m.value_mm <= 0:
            out.append(DimComparison(name, None, target, None, tol, NEEDS_REVIEW, 0.0))
            continue
        dev = m.value_mm - target
        if m.confidence < _MIN_CONFIDENCE:
            status = NEEDS_REVIEW
        elif abs(dev) <= tol:
            status = PASS
        else:
            status = FAIL
        out.append(DimComparison(name, m.value_mm, target, dev, tol, status, m.confidence))
    return out
