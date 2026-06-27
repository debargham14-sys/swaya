"""Persist scan sessions in DynamoDB.

The ``scans`` table holds JSON metadata (one item per scan, keyed by ``scan_id``).
Bundle ZIPs and raw capture photos are stored as blobs in S3 (cloud) or on disk
(local dev) — see ``api.storage.photo_store`` — with their location recorded on
the item.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from boto3.dynamodb.conditions import Attr, Key

from api.db.dynamo import from_item, get_table, to_item
from api.storage.photo_store import open_bundle as open_stored_bundle
from api.storage.photo_store import open_photo as open_stored_photo
from api.storage.photo_store import serialize_photos, store_bundle, store_photos


class ScanRepository:
    TABLE = "scans"

    def __init__(self) -> None:
        self._table = get_table(self.TABLE)

    @staticmethod
    def new_id() -> str:
        return str(uuid4())

    def insert_scan(
        self,
        *,
        scan_id: str,
        mode: str,
        height_cm: float,
        weight_kg: float | None,
        prefer: str,
        measurements: dict[str, Any],
        manifest: dict[str, Any],
        mesh_included: bool,
        bundle_bytes: bytes,
        bundle_filename: str,
        photo_files: dict[str, Path] | None = None,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        doc: dict[str, Any] = {
            "scan_id": scan_id,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
            "mode": mode,
            "height_cm": height_cm,
            "weight_kg": weight_kg,
            "prefer": prefer,
            "measurements": measurements,
            "manifest": manifest,
            "mesh_included": mesh_included,
        }

        # Optional data-collection metadata (subject label, collector, consent, notes).
        for key, value in (metadata or {}).items():
            if value is not None:
                doc[key] = value

        doc.update(store_bundle(scan_id, bundle_filename, bundle_bytes))
        doc["photos"] = store_photos(scan_id, photo_files or {})

        self._table.put_item(Item=to_item(doc))
        return self._serialize(doc)

    def _get(self, scan_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        """Fetch a scan item, enforcing ownership when a user is known."""
        resp = self._table.get_item(Key={"scan_id": scan_id})
        item = resp.get("Item")
        if not item:
            return None
        doc = from_item(item)
        if user_id and doc.get("user_id") not in (None, user_id):
            return None
        return doc

    def get_scan(self, scan_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        doc = self._get(scan_id, user_id)
        return self._serialize(doc) if doc else None

    def list_scans(self, limit: int = 30, user_id: str | None = None) -> list[dict[str, Any]]:
        # NOTE: low-volume beta data collection — a full scan + in-app sort is fine.
        # TODO: add a GSI (constant PK + created_at sort key) before this scales.
        scan_kwargs: dict[str, Any] = {}
        if user_id:
            scan_kwargs["FilterExpression"] = Attr("user_id").eq(user_id)
        items: list[dict[str, Any]] = []
        resp = self._table.scan(**scan_kwargs)
        items.extend(resp.get("Items", []))
        while "LastEvaluatedKey" in resp:
            resp = self._table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **scan_kwargs)
            items.extend(resp.get("Items", []))
        docs = [from_item(it) for it in items]
        docs.sort(key=lambda d: d.get("created_at") or "", reverse=True)
        return [self._serialize(d) for d in docs[: max(0, limit)]]

    def update_ground_truth(
        self, scan_id: str, ground_truth_cm: dict[str, float], user_id: str | None = None
    ) -> dict[str, Any] | None:
        """Store tape-measured girths (cm) for training / calibration."""
        doc = self._get(scan_id, user_id)
        if not doc:
            return None
        cleaned = {k: float(v) for k, v in ground_truth_cm.items() if v is not None and v > 0}
        now = datetime.now(timezone.utc).isoformat()
        measurements = dict(doc.get("measurements") or {})
        predicted = measurements.get("girths_cm") or {}
        comparison: dict[str, Any] = {}
        for level, tape_cm in cleaned.items():
            pred = predicted.get(level)
            if pred is not None:
                comparison[level] = {
                    "predicted_cm": round(float(pred), 1),
                    "tape_cm": round(tape_cm, 1),
                    "error_cm": round(tape_cm - float(pred), 1),
                }
        self._table.update_item(
            Key={"scan_id": scan_id},
            UpdateExpression=(
                "SET ground_truth_cm = :gt, ground_truth_comparison = :cmp, "
                "ground_truth_saved_at = :ts, updated_at = :ts"
            ),
            ExpressionAttributeValues=to_item(
                {":gt": cleaned, ":cmp": comparison, ":ts": now}
            ),
        )
        return self.get_scan(scan_id)

    def open_bundle(
        self, scan_id: str, user_id: str | None = None
    ) -> tuple[BinaryIO | Path, str, int] | None:
        """Return (stream-or-path, filename, size_bytes) for the bundle ZIP."""
        doc = self._get(scan_id, user_id)
        return open_stored_bundle(doc) if doc else None

    def open_photo(
        self, scan_id: str, view: str, user_id: str | None = None
    ) -> tuple[BinaryIO, str, str] | None:
        """Return (stream, filename, content_type) for a raw capture photo."""
        doc = self._get(scan_id, user_id)
        return open_stored_photo(doc, view) if doc else None

    @staticmethod
    def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
        out = dict(doc)
        out.pop("bundle_path", None)
        out["photos"] = serialize_photos(out.get("photos"))
        return out
