"""Photo storage: GridFS (default) or S3 with MongoDB metadata links."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO

from api.db.mongo import get_bucket
from api.settings import (
    AWS_ACCESS_KEY_ID,
    AWS_REGION,
    AWS_SECRET_ACCESS_KEY,
    PHOTO_STORAGE,
    S3_BUCKET,
    S3_PHOTO_PREFIX,
)

logger = logging.getLogger(__name__)


class PhotoStorageError(RuntimeError):
    """Raised when photo storage is misconfigured or upload fails."""


_CONTENT_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def _content_type(filename: str) -> str:
    return _CONTENT_TYPES.get(Path(filename).suffix.lower(), "image/jpeg")


def _s3_client():
    import boto3  # noqa: PLC0415 — optional dependency

    kwargs: dict[str, str] = {"region_name": AWS_REGION}
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = AWS_SECRET_ACCESS_KEY
    return boto3.client("s3", **kwargs)


def s3_configured() -> bool:
    return PHOTO_STORAGE == "s3" and bool(S3_BUCKET)


def photo_storage_status() -> dict[str, Any]:
    """Health-check payload for /health."""
    if PHOTO_STORAGE != "s3":
        return {"backend": PHOTO_STORAGE, "ready": True}
    missing = []
    if not S3_BUCKET:
        missing.append("S3_BUCKET")
    if not AWS_ACCESS_KEY_ID:
        missing.append("AWS_ACCESS_KEY_ID")
    if not AWS_SECRET_ACCESS_KEY:
        missing.append("AWS_SECRET_ACCESS_KEY")
    return {
        "backend": "s3",
        "ready": not missing,
        "bucket": S3_BUCKET or None,
        "region": AWS_REGION,
        "prefix": S3_PHOTO_PREFIX,
        "missing": missing,
    }


def store_photos(scan_id: str, photo_files: dict[str, Path]) -> dict[str, Any]:
    if PHOTO_STORAGE == "s3":
        if not s3_configured():
            raise PhotoStorageError(
                "PHOTO_STORAGE=s3 but S3 is not configured — set S3_BUCKET, "
                "AWS_ACCESS_KEY_ID, and AWS_SECRET_ACCESS_KEY"
            )
        return _store_photos_s3(scan_id, photo_files)
    return _store_photos_gridfs(scan_id, photo_files)


def _store_photos_gridfs(scan_id: str, photo_files: dict[str, Path]) -> dict[str, Any]:
    bucket = get_bucket()
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
            "storage": "gridfs",
            "file_id": file_id,
            "filename": filename,
            "content_type": _content_type(filename),
        }
    return photos


def _store_photos_s3(scan_id: str, photo_files: dict[str, Path]) -> dict[str, Any]:
    client = _s3_client()
    photos: dict[str, Any] = {}
    prefix = S3_PHOTO_PREFIX.strip("/")

    for view, path in photo_files.items():
        if not path or not Path(path).is_file():
            continue
        filename = f"{view}{Path(path).suffix or '.jpg'}"
        key = f"{prefix}/{scan_id}/photos/{filename}"
        content_type = _content_type(filename)
        client.upload_file(
            str(path),
            S3_BUCKET,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        url = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{key}"
        photos[view] = {
            "storage": "s3",
            "s3_bucket": S3_BUCKET,
            "s3_key": key,
            "s3_url": url,
            "filename": filename,
            "content_type": content_type,
        }
        logger.info("photo stored s3://%s/%s", S3_BUCKET, key)

    return photos


def open_photo(scan_doc: dict[str, Any], view: str) -> tuple[BinaryIO, str, str] | None:
    photo = (scan_doc.get("photos") or {}).get(view)
    if not photo:
        return None

    storage = photo.get("storage", "gridfs")
    filename = photo.get("filename", f"{view}.jpg")
    content_type = photo.get("content_type", "image/jpeg")

    if storage == "s3" and photo.get("s3_bucket") and photo.get("s3_key"):
        client = _s3_client()
        buf = BytesIO()
        client.download_fileobj(photo["s3_bucket"], photo["s3_key"], buf)
        buf.seek(0)
        return buf, filename, content_type

    file_id = photo.get("file_id")
    if file_id is None:
        return None
    stream = get_bucket().open_download_stream(file_id)
    return stream, filename, content_type


def serialize_photos(photos: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(photos, dict):
        return photos
    out: dict[str, Any] = {}
    for view, meta in photos.items():
        if not isinstance(meta, dict):
            continue
        entry = dict(meta)
        if entry.get("file_id") is not None:
            entry["file_id"] = str(entry["file_id"])
        out[view] = entry
    return out
