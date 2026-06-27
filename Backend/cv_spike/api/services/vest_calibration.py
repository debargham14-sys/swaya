"""
Vest calibration feedback loop.

As tailors submit tape ground truth alongside scans, this re-fits the single
global calibration factor (girth = pi * width * factor) from the accumulated
(estimate, ground-truth) pairs. The active factor is stored in DynamoDB and used
by new measurements; it falls back to the code default when unset/offline.

Flow: scans accumulate ground truth -> POST /v1/vest/calibration/recompute
re-fits + (optionally) applies -> future scans use the improved factor.
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr

from api.db.dynamo import dynamo_available, from_item, get_table, to_item
from api.services.vest_service import VEST_TABLE
from pipeline.measure.vest_charuco import VEST_CALIBRATION_FACTOR

logger = logging.getLogger(__name__)

CALIB_TABLE = "vest_calibration"
_ACTIVE_ID = "active"
_BANDS = ("bust", "waist", "hip")


def active_factor() -> float:
    """Current calibration factor — DB-stored if present, else the code default."""
    if not dynamo_available():
        return VEST_CALIBRATION_FACTOR
    try:
        item = get_table(CALIB_TABLE).get_item(Key={"id": _ACTIVE_ID}).get("Item")
        doc = from_item(item) if item else None
        if doc and isinstance(doc.get("factor"), (int, float)):
            return float(doc["factor"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("active_factor read failed: %s", exc)
    return VEST_CALIBRATION_FACTOR


def _gather_pairs() -> list[dict[str, Any]]:
    """One record per (scan, band) with a stored estimate AND a tape ground truth."""
    table = get_table(VEST_TABLE)
    items: list[dict[str, Any]] = []
    resp = table.scan(FilterExpression=Attr("ground_truth_in").exists() & Attr("ground_truth_in").ne(None))
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(
            FilterExpression=Attr("ground_truth_in").exists() & Attr("ground_truth_in").ne(None),
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        items.extend(resp.get("Items", []))
    pairs: list[dict[str, Any]] = []
    for s in (from_item(it) for it in items):
        m = s.get("measurement") or {}
        gt = s.get("ground_truth_in") or {}
        cf = float(m.get("calibration_factor") or VEST_CALIBRATION_FACTOR)
        est_in = m.get("girths_in") or {}
        for band in _BANDS:
            e, g = est_in.get(band), gt.get(f"{band}_in")
            if isinstance(e, (int, float)) and isinstance(g, (int, float)) and e > 0 and cf > 0:
                raw = e / cf  # remove the calibration that was applied -> raw estimate
                pairs.append({
                    "scan_id": s.get("scan_id"), "band": band,
                    "raw_in": raw, "gt_in": float(g), "ratio": float(g) / raw,
                })
    return pairs


def recompute_calibration(apply: bool = False) -> dict[str, Any]:
    """Re-fit the global factor from ground-truth pairs; optionally persist it."""
    current = active_factor()
    if not dynamo_available():
        return {"samples": 0, "current_factor": current, "applied": False, "reason": "dynamo_unavailable"}

    pairs = _gather_pairs()
    n = len(pairs)
    if n == 0:
        return {"samples": 0, "current_factor": current, "applied": False,
                "reason": "no ground-truth pairs yet"}

    suggested = float(statistics.median(p["ratio"] for p in pairs))

    def _err(factor: float) -> float:
        e = [abs(p["raw_in"] * factor - p["gt_in"]) / p["gt_in"] for p in pairs]
        return round(100 * sum(e) / len(e), 2)

    per_band = {
        b: round(float(statistics.median([p["ratio"] for p in pairs if p["band"] == b])), 4)
        for b in _BANDS if any(p["band"] == b for p in pairs)
    }
    result = {
        "samples": n,
        "scans": len({p["scan_id"] for p in pairs}),
        "current_factor": round(current, 4),
        "suggested_factor": round(suggested, 4),
        "mean_abs_error_pct": {"current": _err(current), "suggested": _err(suggested)},
        "per_band_factor": per_band,
        "applied": False,
    }

    if apply:
        get_table(CALIB_TABLE).put_item(
            Item=to_item({
                "id": _ACTIVE_ID,
                "factor": suggested,
                "samples": n,
                "fitted_at": datetime.now(timezone.utc).isoformat(),
                "mean_abs_error_pct": result["mean_abs_error_pct"]["suggested"],
            })
        )
        result["applied"] = True
        logger.info("vest calibration applied: %.4f from %d samples", suggested, n)
    return result
