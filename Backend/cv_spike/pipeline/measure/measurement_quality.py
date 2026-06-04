"""Reject and hide implausible girths (pose failure + loose clothing)."""

from __future__ import annotations

from pipeline.measure.calibration import girths_are_plausible
from pipeline.measure.measure_engine import EngineResult

_POSE_DEGRADED = (
    "pose_not_detected",
    "pose_error:",
    "segmentation_fallback_grabcut",
    "segmentation_grabcut_only",
    "slice_sweep:pose_fallback",
)


def cv_degraded(warnings: list[str]) -> bool:
    text = " ".join(warnings).lower()
    return any(m in text for m in _POSE_DEGRADED)


def apply_quality_gate(result: EngineResult) -> EngineResult:
    """Keep raw girths for debugging but clear displayed values when untrustworthy."""
    if not result.girths_cm:
        return result
    if girths_are_plausible(result.girths_cm) and not cv_degraded(result.warnings):
        return result

    if not result.girths_raw_cm:
        result.girths_raw_cm = dict(result.girths_cm)
    result.girths_cm = {}
    result.confidence = min(result.confidence, 0.12)
    if "measurements_unreliable:retake_required" not in result.warnings:
        result.warnings.append("measurements_unreliable:retake_required")
    return result
