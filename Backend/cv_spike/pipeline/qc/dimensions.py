"""
Stage 4 - Direct dimensional measurement.

Uses the framework mm coordinate system as ground truth to measure the blouse's
critical dimensions. Linear dimensions (shoulder width, length, across-front,
armhole depth) are measured directly. Circumference dimensions (bust, underbust,
waist) are estimated from the flat-lay half-width as ``2 x width`` and reported
so the compare stage can match them against the order's circumference targets.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pipeline.qc.landmarks import Landmarks, _row_extent

# kind: "linear" measured as-is; "circumference" = 2 x flat half-width.
DIMENSION_KINDS = {
    "shoulder_width": "linear",
    "total_length": "linear",
    "across_front": "linear",
    "armhole_depth": "linear",
    "bust": "circumference",
    "underbust": "circumference",
}


@dataclass
class Measurement:
    name: str
    value_mm: float
    kind: str
    confidence: float


@dataclass
class DimensionSet:
    measurements: dict[str, Measurement] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def value(self, name: str) -> float | None:
        m = self.measurements.get(name)
        return m.value_mm if m else None

    def to_dict(self) -> dict:
        return {
            "measurements_mm": {k: round(m.value_mm, 1) for k, m in self.measurements.items()},
            "kinds": {k: m.kind for k, m in self.measurements.items()},
            "confidence": {k: round(m.confidence, 2) for k, m in self.measurements.items()},
            "warnings": self.warnings,
        }


def measure_dimensions(lm: Landmarks) -> DimensionSet:
    ds = DimensionSet()
    scale = lm.mm_scale

    def add(name: str, value_mm: float, conf: float) -> None:
        ds.measurements[name] = Measurement(name, round(value_mm, 1), DIMENSION_KINDS[name], conf)

    # Linear
    add("shoulder_width", lm.width_profile_mm.get("shoulder", 0.0), 0.8)
    add("total_length", (lm.bottom_y - lm.shoulder_y) / scale, 0.85)
    add("across_front", lm.width_profile_mm.get("chest", 0.0), 0.65)
    add("armhole_depth", (lm.underarm_y - lm.shoulder_y) / scale, 0.6)

    # Circumference (2 x flat width)
    bust_w = lm.width_profile_mm.get("bust", 0.0)
    underbust_w = lm.width_profile_mm.get("underbust", 0.0)
    add("bust", 2.0 * bust_w, 0.7)
    add("underbust", 2.0 * underbust_w, 0.7)

    for name, m in ds.measurements.items():
        if m.value_mm <= 0:
            ds.warnings.append(f"{name}_not_measurable")
            m.confidence = 0.1
    return ds
