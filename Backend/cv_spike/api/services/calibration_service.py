"""Learn affine girth calibration from saved ground truth; apply on new scans."""

from __future__ import annotations

import logging
from typing import Any

from api.db.calibration import CalibrationRepository
from api.db.scans import ScanRepository
from pipeline.measure.calibration import (
    GIRTH_LEVELS,
    CalibrationProfile,
    apply_girth_calibration,
    fit_profile,
    girths_are_plausible,
    profile_is_sane,
)
from pipeline.measure.measure_engine import EngineResult

logger = logging.getLogger("swaya.calibration")

_POSE_DEGRADED_MARKERS = (
    "pose_not_detected",
    "pose_error:no_pose",
    "slice_sweep:pose_fallback",
)


def _raw_girths_from_measurements(measurements: dict[str, Any]) -> dict[str, float]:
    raw = measurements.get("girths_raw_cm")
    if isinstance(raw, dict) and raw:
        return {k: float(v) for k, v in raw.items() if k in GIRTH_LEVELS}
    girths = measurements.get("girths_cm") or {}
    return {k: float(v) for k, v in girths.items() if k in GIRTH_LEVELS}


def _warnings_indicate_bad_cv(warnings: list[str] | None) -> bool:
    if not warnings:
        return False
    text = " ".join(str(w) for w in warnings).lower()
    return any(m in text for m in _POSE_DEGRADED_MARKERS)


def collect_training_data(limit: int = 500) -> tuple[dict[str, float], dict[str, float], int]:
    """Aggregate (raw, tape) pairs from scans with plausible CV + ground truth."""
    repo = ScanRepository()
    col = repo._col  # noqa: SLF001 — training query
    cursor = col.find(
        {"ground_truth_cm": {"$exists": True, "$ne": {}}},
        {"measurements": 1, "ground_truth_cm": 1},
    ).sort("ground_truth_saved_at", -1).limit(limit)

    raw_all: dict[str, list[float]] = {k: [] for k in GIRTH_LEVELS}
    tape_all: dict[str, list[float]] = {k: [] for k in GIRTH_LEVELS}
    scan_count = 0

    for doc in cursor:
        gt = doc.get("ground_truth_cm") or {}
        m = doc.get("measurements") or {}
        if _warnings_indicate_bad_cv(m.get("warnings")):
            continue
        raw = _raw_girths_from_measurements(m)
        if not raw or not gt or not girths_are_plausible(raw):
            continue
        if not girths_are_plausible({k: float(v) for k, v in gt.items() if v}):
            continue
        scan_count += 1
        for level in GIRTH_LEVELS:
            if level in raw and level in gt:
                raw_all[level].append(float(raw[level]))
                tape_all[level].append(float(gt[level]))

    anchors: dict[str, float] = {}
    raw_mean: dict[str, float] = {}
    for level in GIRTH_LEVELS:
        if tape_all[level]:
            anchors[level] = sum(tape_all[level]) / len(tape_all[level])
        if raw_all[level]:
            raw_mean[level] = sum(raw_all[level]) / len(raw_all[level])

    if not (set(anchors) & set(raw_mean)):
        return {}, {}, 0
    return raw_mean, anchors, scan_count


def retrain_global_profile() -> CalibrationProfile | None:
    raw_mean, anchors, scan_count = collect_training_data()
    if not anchors or not raw_mean:
        logger.info("calibration: no eligible ground-truth scans — skipping fit")
        return None

    profile = fit_profile(
        anchors,
        raw_mean,
        name="global",
        notes=f"fit from {scan_count} scans with tape ground truth",
    )
    if not profile_is_sane(profile):
        logger.warning(
            "calibration: rejected insane profile scale=%.3f offset=%.1f raw=%s",
            profile.scale,
            profile.offset_cm,
            profile.raw_girths_cm,
        )
        return None

    pair_count = len(set(anchors) & set(raw_mean))
    CalibrationRepository().save_global(
        profile,
        training_scans=scan_count,
        training_pairs=pair_count,
    )
    logger.info(
        "calibration: global profile updated scale=%.4f offset=%.2f scans=%d pairs=%d",
        profile.scale,
        profile.offset_cm,
        scan_count,
        pair_count,
    )
    return profile


def clear_global_profile() -> bool:
    return CalibrationRepository().clear_global()


def get_global_profile() -> CalibrationProfile | None:
    profile = CalibrationRepository().get_global()
    if profile and not profile_is_sane(profile):
        logger.warning("calibration: ignoring stale insane global profile in DB")
        return None
    return profile


def _should_apply_profile(result: EngineResult, profile: CalibrationProfile) -> bool:
    if _warnings_indicate_bad_cv(result.warnings):
        return False
    if not girths_are_plausible(result.girths_cm):
        return False
    return profile_is_sane(profile)


def apply_to_engine_result(result: EngineResult) -> EngineResult:
    profile = get_global_profile()
    if not result.girths_raw_cm and result.girths_cm:
        result.girths_raw_cm = dict(result.girths_cm)
    if not profile:
        return result
    if not _should_apply_profile(result, profile):
        if "calibration_skipped:cv_degraded" not in result.warnings:
            result.warnings.append("calibration_skipped:cv_degraded")
        return result

    result.girths_cm = apply_girth_calibration(result.girths_raw_cm, profile)
    result.calibration_profile = profile.name
    if "calibrated:global_affine" not in result.warnings:
        result.warnings.append("calibrated:global_affine")
    return result


def apply_to_measurements_dict(measurements: dict[str, Any]) -> dict[str, Any]:
    profile = get_global_profile()
    if not profile:
        return measurements

    raw = _raw_girths_from_measurements(measurements)
    if not raw or not girths_are_plausible(raw):
        return measurements
    if _warnings_indicate_bad_cv(measurements.get("warnings")):
        return measurements

    out = dict(measurements)
    out["girths_raw_cm"] = raw
    out["girths_cm"] = apply_girth_calibration(raw, profile)
    out["girths_in"] = {k: round(v / 2.54, 1) for k, v in out["girths_cm"].items()}
    out["calibration_profile"] = profile.name
    meta = CalibrationRepository().get_global_meta()
    if meta:
        out["calibration_training_scans"] = meta.get("training_scans")
    return out


def refresh_scan_after_ground_truth(scan_id: str) -> dict[str, Any] | None:
    """Retrain global profile and re-apply calibrated girths to this scan."""
    profile = retrain_global_profile()
    repo = ScanRepository()
    doc = repo.get_scan(scan_id)
    if not doc:
        return None

    m = dict(doc.get("measurements") or {})
    if profile and not _warnings_indicate_bad_cv(m.get("warnings")):
        m = apply_to_measurements_dict(m)
    else:
        m.setdefault("girths_raw_cm", _raw_girths_from_measurements(m))

    comparison = _comparison(m.get("girths_cm") or {}, doc.get("ground_truth_cm") or {})
    repo._col.update_one(  # noqa: SLF001
        {"_id": scan_id},
        {"$set": {"measurements": m, "ground_truth_comparison": comparison}},
    )
    return repo.get_scan(scan_id)


def _comparison(predicted: dict[str, Any], ground_truth: dict[str, float]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for level, tape_cm in ground_truth.items():
        pred = predicted.get(level)
        if pred is not None:
            out[level] = {
                "predicted_cm": round(float(pred), 1),
                "tape_cm": round(float(tape_cm), 1),
                "error_cm": round(float(tape_cm) - float(pred), 1),
            }
    return out
