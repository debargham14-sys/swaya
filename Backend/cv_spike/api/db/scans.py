"""Persist scan sessions in MongoDB.

Bundle ZIPs and raw capture photos are stored in GridFS by default
(``SCAN_STORAGE_BACKEND=gridfs``) so every byte lives in the cloud database and
survives hosts with an ephemeral filesystem. Set ``SCAN_STORAGE_BACKEND=disk``
to keep the legacy on-disk ZIP behaviour for local development.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from api.db.mongo import get_bucket, get_db
from api.settings import SCAN_STORAGE_BACKEND, SCAN_STORAGE_DIR

_CONTENT_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def _content_type(filename: str) -> str:
    return _CONTENT_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream")


class ScanRepository:
    COLLECTION = "scans"

    def __init__(self) -> None:
        self._col = get_db()[self.COLLECTION]
        self._use_gridfs = SCAN_STORAGE_BACKEND != "disk"
        if not self._use_gridfs:
            SCAN_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

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
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "_id": scan_id,
            "scan_id": scan_id,
            "created_at": now,
            "updated_at": now,
            "mode": mode,
            "height_cm": height_cm,
            "weight_kg": weight_kg,
            "prefer": prefer,
            "measurements": measurements,
            "manifest": manifest,
            "mesh_included": mesh_included,
            "bundle_filename": bundle_filename,
            "bundle_size_bytes": len(bundle_bytes),
            "storage_backend": "gridfs" if self._use_gridfs else "disk",
        }

        # Optional data-collection metadata (subject label, collector, consent, notes).
        for key, value in (metadata or {}).items():
            if value is not None:
                doc[key] = value

        if self._use_gridfs:
            bucket = get_bucket()
            bundle_id = bucket.upload_from_stream(
                f"{scan_id}/{bundle_filename}",
                bundle_bytes,
                metadata={"scan_id": scan_id, "kind": "bundle"},
            )
            doc["bundle_file_id"] = bundle_id
            doc["photos"] = self._store_photos_gridfs(bucket, scan_id, photo_files or {})
        else:
            storage = SCAN_STORAGE_DIR / scan_id
            storage.mkdir(parents=True, exist_ok=True)
            bundle_path = storage / bundle_filename
            bundle_path.write_bytes(bundle_bytes)
            doc["bundle_path"] = str(bundle_path.resolve())

        self._col.insert_one(doc)
        return self._serialize(doc)

    def _store_photos_gridfs(
        self, bucket: Any, scan_id: str, photo_files: dict[str, Path]
    ) -> dict[str, Any]:
        photos: dict[str, Any] = {}
        for view, path in photo_files.items():
            if not path or not Path(path).is_file():
                continue
            filename = f"{view}{Path(path).suffix or '.jpg'}"
            file_id = bucket.upload_from_stream(
                f"{scan_id}/photos/{filename}",
                Path(path).read_bytes(),
                metadata={"scan_id": scan_id, "kind": "photo", "view": view},
            )
            photos[view] = {
                "file_id": file_id,
                "filename": filename,
                "content_type": _content_type(filename),
            }
        return photos

    def get_scan(self, scan_id: str) -> dict[str, Any] | None:
        doc = self._col.find_one({"_id": scan_id})
        return self._serialize(doc) if doc else None

    def list_scans(self, limit: int = 30) -> list[dict[str, Any]]:
        cursor = self._col.find().sort("created_at", -1).limit(limit)
        return [self._serialize(d) for d in cursor]

    def update_ground_truth(
        self, scan_id: str, ground_truth_cm: dict[str, float]
    ) -> dict[str, Any] | None:
        """Store tape-measured girths (cm) for training / calibration."""
        doc = self._col.find_one({"_id": scan_id})
        if not doc:
            return None
        cleaned = {k: float(v) for k, v in ground_truth_cm.items() if v is not None and v > 0}
        now = datetime.now(timezone.utc)
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
        self._col.update_one(
            {"_id": scan_id},
            {
                "$set": {
                    "ground_truth_cm": cleaned,
                    "ground_truth_comparison": comparison,
                    "ground_truth_saved_at": now,
                    "updated_at": now,
                }
            },
        )
        return self.get_scan(scan_id)

    def open_bundle(self, scan_id: str) -> tuple[BinaryIO | Path, str, int] | None:
        """Return (stream-or-path, filename, size_bytes) for the bundle ZIP."""
        doc = self._col.find_one({"_id": scan_id})
        if not doc:
            return None
        filename = doc.get("bundle_filename") or f"{scan_id}.zip"
        size = int(doc.get("bundle_size_bytes", 0) or 0)
        if doc.get("bundle_file_id") is not None:
            stream = get_bucket().open_download_stream(doc["bundle_file_id"])
            return stream, filename, size
        path = Path(doc.get("bundle_path", ""))
        return (path, filename, size) if path.is_file() else None

    def open_photo(self, scan_id: str, view: str) -> tuple[BinaryIO, str, str] | None:
        """Return (stream, filename, content_type) for a raw capture photo (GridFS only)."""
        doc = self._col.find_one({"_id": scan_id})
        if not doc:
            return None
        photo = (doc.get("photos") or {}).get(view)
        if not photo or photo.get("file_id") is None:
            return None
        stream = get_bucket().open_download_stream(photo["file_id"])
        return stream, photo.get("filename", f"{view}.jpg"), photo.get("content_type", "image/jpeg")

    @staticmethod
    def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
        out = dict(doc)
        out.pop("_id", None)
        out.pop("bundle_path", None)
        for key in ("created_at", "updated_at"):
            val = out.get(key)
            if isinstance(val, datetime):
                out[key] = val.isoformat()
        # GridFS ObjectIds are not JSON serialisable; expose as strings.
        if out.get("bundle_file_id") is not None:
            out["bundle_file_id"] = str(out["bundle_file_id"])
        photos = out.get("photos")
        if isinstance(photos, dict):
            out["photos"] = {
                view: {**meta, "file_id": str(meta["file_id"])}
                for view, meta in photos.items()
                if isinstance(meta, dict) and meta.get("file_id") is not None
            }
        return out
