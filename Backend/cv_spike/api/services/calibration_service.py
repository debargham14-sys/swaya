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
)
from pipeline.measure.measure_engine import EngineResult

logger = logging.getLogger("swaya.calibration")


def _raw_girths_from_measurements(measurements: dict[str, Any]) -> dict[str, float]:
    raw = measurements.get("girths_raw_cm")
    if isinstance(raw, dict) and raw:
        return {k: float(v) for k, v in raw.items() if k in GIRTH_LEVELS}
    girths = measurements.get("girths_cm") or {}
    return {k: float(v) for k, v in girths.items() if k in GIRTH_LEVELS}


def collect_training_data(limit: int = 500) -> tuple[dict[str, float], dict[str, float], int]:
    """Aggregate (raw, tape) pairs from all scans that have ground truth."""
    repo = ScanRepository()
    col = repo._col  # noqa: SLF001 — training query
    cursor = col.find(
        {"ground_truth_cm": {"$exists": True, "$ne": {}}},
        {"measurements": 1, "ground_truth_cm": 1},
    ).sort("ground_truth_cm_saved_at", -1).limit(limit)

    raw_all: dict[str, list[float]] = {k: [] for k in GIRTH_LEVELS}
    tape_all: dict[str, list[float]] = {k: [] for k in GIRTH_LEVELS}
    scan_count = 0

    for doc in cursor:
        gt = doc.get("ground_truth_cm") or {}
        m = doc.get("measurements") or {}
        raw = _raw_girths_from_measurements(m)
        if not raw or not gt:
            continue
        scan_count += 1
        for level in GIRTH_LEVELS:
            if level in raw and level in gt:
                raw_all[level].append(float(raw[level]))
                tape_all[level].append(float(gt[level]))

    # Mean per level across scans (stable when multiple subjects).
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
        logger.info("calibration: no ground-truth scans yet — skipping fit")
        return None

    profile = fit_profile(
        anchors,
        raw_mean,
        name="global",
        notes=f"fit from {scan_count} scans with tape ground truth",
    )
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


def get_global_profile() -> CalibrationProfile | None:
    return CalibrationRepository().get_global()


def apply_to_engine_result(result: EngineResult) -> EngineResult:
    profile = get_global_profile()
    if not profile:
        if not result.girths_raw_cm and result.girths_cm:
            result.girths_raw_cm = dict(result.girths_cm)
        return result

    if not result.girths_raw_cm:
        result.girths_raw_cm = dict(result.girths_cm)
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
    if not raw:
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
    if profile:
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
