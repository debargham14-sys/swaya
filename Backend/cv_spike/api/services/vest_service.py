"""
Vest ChArUco scan service (BETA) — measure + persist for tailor data collection.

Stores each capture (photos + beta measurement + optional tape ground truth) in a
dedicated ``vest_scans`` MongoDB collection, independent of the main scan flow.
Degrades gracefully: if MongoDB is unavailable the measurement still returns,
just unstored.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import cv2

from api.db.mongo import get_db, mongo_available
from api.storage.photo_store import serialize_photos, store_photos
from pipeline.measure.vest_charuco import measure_vest_front

logger = logging.getLogger(__name__)

VEST_COLLECTION = "vest_scans"
MM_PER_IN = 25.4


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
    img = cv2.imread(str(front)) if front and Path(front).is_file() else None
    if img is None:
        measurement = {"warnings": ["cannot_read_front_image"], "measurements_reliable": False}
    else:
        from api.services.vest_calibration import active_factor

        measurement = measure_vest_front(img, calibration_factor=active_factor()).to_dict()

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

    if mongo_available():
        try:
            present = {k: v for k, v in paths.items() if v and Path(v).is_file()}
            photos = store_photos(scan_id, present)
            record = {**doc, "photos": photos}
            get_db()[VEST_COLLECTION].insert_one(record)
            doc["photos"] = serialize_photos(photos)
            doc["stored"] = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("vest scan %s persist failed: %s", scan_id, exc)
            doc["persist_error"] = str(exc)

    return doc


def list_vest_scans(limit: int = 30) -> list[dict[str, Any]]:
    cur = (
        get_db()[VEST_COLLECTION]
        .find({}, {"_id": 0, "photos": 0})
        .sort("created_at", -1)
        .limit(max(1, min(limit, 200)))
    )
    return list(cur)


def get_vest_scan(scan_id: str) -> dict[str, Any] | None:
    return get_db()[VEST_COLLECTION].find_one({"scan_id": scan_id}, {"_id": 0, "photos": 0})


def save_vest_ground_truth(scan_id: str, ground_truth_in: dict[str, float]) -> dict[str, Any] | None:
    """Attach tape-measured girths (inches) to a stored scan for calibration."""
    from pymongo import ReturnDocument

    return get_db()[VEST_COLLECTION].find_one_and_update(
        {"scan_id": scan_id},
        {"$set": {"ground_truth_in": ground_truth_in}},
        projection={"_id": 0, "photos": 0},
        return_document=ReturnDocument.AFTER,
    )
