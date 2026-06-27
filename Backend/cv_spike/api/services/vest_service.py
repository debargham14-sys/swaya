"""
Vest ChArUco scan service (BETA) — measure + persist for tailor data collection.

Stores each capture (photos + beta measurement + optional tape ground truth) in a
dedicated ``vest_scans`` DynamoDB table, independent of the main scan flow.
Degrades gracefully: if DynamoDB is unavailable the measurement still returns,
just unstored.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import cv2

from api.db.dynamo import dynamo_available, from_item, get_table, to_item
from api.storage.photo_store import serialize_photos, store_photos
from pipeline.measure.vest_charuco import measure_vest_views

logger = logging.getLogger(__name__)

VEST_TABLE = "vest_scans"
MM_PER_IN = 25.4


def _strip(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    """Public view of a vest record: plain Python, without the stored photos blob."""
    if not doc:
        return None
    out = from_item(doc)
    out.pop("photos", None)
    return out


def _new_scan_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"vest_{stamp}_{uuid.uuid4().hex[:6]}"


def process_vest_scan(
    paths: dict[str, Path],
    *,
    subject_label: Optional[str] = None,
    collector_id: Optional[str] = None,
    consent_given: Optional[bool] = None,
    notes: Optional[str] = None,
    ground_truth_in: Optional[dict[str, float]] = None,
) -> dict[str, Any]:
    """Measure the front vest photo, persist the record, return a JSON-safe doc."""
    front = paths.get("front")
    back = paths.get("back")
    fimg = cv2.imread(str(front)) if front and Path(front).is_file() else None
    bimg = cv2.imread(str(back)) if back and Path(back).is_file() else None
    if fimg is None and bimg is None:
        measurement = {"warnings": ["cannot_read_images"], "measurements_reliable": False}
    else:
        from api.services.vest_calibration import active_factor

        measurement = measure_vest_views(
            front_bgr=fimg, back_bgr=bimg, calibration_factor=active_factor()
        ).to_dict()

    scan_id = _new_scan_id()
    doc: dict[str, Any] = {
        "scan_id": scan_id,
        "kind": "vest",
        "beta": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "subject_label": subject_label,
        "collector_id": collector_id,
        "consent_given": consent_given,
        "notes": notes,
        "measurement": measurement,
        "ground_truth_in": ground_truth_in or None,
        "stored": False,
    }

    if dynamo_available():
        try:
            present = {k: v for k, v in paths.items() if v and Path(v).is_file()}
            photos = store_photos(scan_id, present)
            record = {**doc, "photos": photos}
            get_table(VEST_TABLE).put_item(Item=to_item(record))
            doc["photos"] = serialize_photos(photos)
            doc["stored"] = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("vest scan %s persist failed: %s", scan_id, exc)
            doc["persist_error"] = str(exc)

    return doc


def list_vest_scans(limit: int = 30) -> list[dict[str, Any]]:
    # Low-volume beta: full scan + in-app sort. TODO: GSI on created_at before scaling.
    table = get_table(VEST_TABLE)
    items: list[dict[str, Any]] = []
    resp = table.scan()
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    docs = [_strip(it) for it in items]
    docs.sort(key=lambda d: d.get("created_at") or "", reverse=True)
    return docs[: max(1, min(limit, 200))]


def get_vest_scan(scan_id: str) -> dict[str, Any] | None:
    item = get_table(VEST_TABLE).get_item(Key={"scan_id": scan_id}).get("Item")
    return _strip(item)


def save_vest_ground_truth(scan_id: str, ground_truth_in: dict[str, float]) -> dict[str, Any] | None:
    """Attach tape-measured girths (inches) to a stored scan for calibration.

    Returns None when no such scan exists (the conditional update fails).
    """
    from botocore.exceptions import ClientError

    try:
        resp = get_table(VEST_TABLE).update_item(
            Key={"scan_id": scan_id},
            UpdateExpression="SET ground_truth_in = :gt",
            ExpressionAttributeValues=to_item({":gt": ground_truth_in}),
            ConditionExpression="attribute_exists(scan_id)",
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return None
        raise
    return _strip(resp.get("Attributes"))
