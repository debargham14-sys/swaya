"""Reject and hide implausible girths (front pose failure or dress blow-up)."""

from __future__ import annotations

from pipeline.measure.calibration import girths_are_plausible
from pipeline.measure.measure_engine import EngineResult


def front_pose_failed(warnings: list[str]) -> bool:
    """True only when the front view did not get pose landmarks/segmentation."""
    for w in warnings:
        s = str(w).lower()
        if "pose_not_detected" in s:
            return True
        if s.startswith("front:") and "pose_error" in s:
            return True
    return False


def apply_quality_gate(result: EngineResult) -> EngineResult:
    """Hide displayed girths only when values are impossible or front pose failed.

    Side/back GrabCut fallback is OK if front pose produced plausible girths.
    """
    if os_disable_quality_gate():
        return result
    if not result.girths_cm:
        return result
    if girths_are_plausible(result.girths_cm) and not front_pose_failed(result.warnings):
        return result

    if not result.girths_raw_cm:
        result.girths_raw_cm = dict(result.girths_cm)
    result.girths_cm = {}
    result.confidence = min(result.confidence, 0.12)
    if "measurements_unreliable:retake_required" not in result.warnings:
        result.warnings.append("measurements_unreliable:retake_required")
    return result


def os_disable_quality_gate() -> bool:
    import os

    return os.environ.get("DISABLE_MEASUREMENT_QUALITY_GATE", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
