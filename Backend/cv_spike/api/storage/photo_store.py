"""Blob storage for scan bundles + raw capture photos: S3 (cloud) or disk (local).

DynamoDB holds only JSON metadata; every binary lives here. Each stored blob is
described by a small dict persisted alongside the scan item, recording where the
bytes went ("s3" + key/url, or "disk" + path) so it can be streamed back later.
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO

from api.settings import (
    AWS_ACCESS_KEY_ID,
    AWS_REGION,
    AWS_SECRET_ACCESS_KEY,
    PHOTO_STORAGE,
    S3_BUCKET,
    S3_PHOTO_PREFIX,
    SCAN_STORAGE_BACKEND,
    SCAN_STORAGE_DIR,
)

logger = logging.getLogger(__name__)


class PhotoStorageError(RuntimeError):
    """Raised when blob storage is misconfigured or an upload fails."""


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
    return bool(S3_BUCKET)


def photo_storage_status() -> dict[str, Any]:
    """Health-check payload for /health."""
    if PHOTO_STORAGE != "s3":
        return {"backend": PHOTO_STORAGE, "ready": True}
    # Only the bucket is required. AWS credentials are resolved from boto3's
    # default chain — static keys (env) OR, in cloud, the EC2 instance role — so
    # the absence of static keys does NOT mean "not ready".
    missing = []
    if not S3_BUCKET:
        missing.append("S3_BUCKET")
    explicit_keys = bool(AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY)
    return {
        "backend": "s3",
        "ready": not missing,
        "bucket": S3_BUCKET or None,
        "region": AWS_REGION,
        "prefix": S3_PHOTO_PREFIX,
        "credentials": "static-keys" if explicit_keys else "default-chain",
        "missing": missing,
    }


def _require_s3() -> None:
    if not s3_configured():
        raise PhotoStorageError(
            "storage backend is 's3' but S3 is not configured — set S3_BUCKET "
            "(AWS credentials come from the default chain / instance role)"
        )


# --- photos -----------------------------------------------------------------

def store_photos(scan_id: str, photo_files: dict[str, Path]) -> dict[str, Any]:
    if PHOTO_STORAGE == "s3":
        _require_s3()
        return _store_photos_s3(scan_id, photo_files)
    return _store_photos_disk(scan_id, photo_files)


def _store_photos_disk(scan_id: str, photo_files: dict[str, Path]) -> dict[str, Any]:
    dest_dir = SCAN_STORAGE_DIR / scan_id / "photos"
    dest_dir.mkdir(parents=True, exist_ok=True)
    photos: dict[str, Any] = {}
    for view, path in photo_files.items():
        if not path or not Path(path).is_file():
            continue
        filename = f"{view}{Path(path).suffix or '.jpg'}"
        dest = dest_dir / filename
        dest.write_bytes(Path(path).read_bytes())
        photos[view] = {
            "storage": "disk",
            "path": str(dest.resolve()),
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
        client.upload_file(str(path), S3_BUCKET, key, ExtraArgs={"ContentType": content_type})
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

    filename = photo.get("filename", f"{view}.jpg")
    content_type = photo.get("content_type", "image/jpeg")
    storage = photo.get("storage", "disk")

    if storage == "s3" and photo.get("s3_bucket") and photo.get("s3_key"):
        buf = BytesIO()
        _s3_client().download_fileobj(photo["s3_bucket"], photo["s3_key"], buf)
        buf.seek(0)
        return buf, filename, content_type

    path = Path(photo.get("path", ""))
    if path.is_file():
        return path.open("rb"), filename, content_type
    return None


def serialize_photos(photos: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strip on-disk absolute paths from the API response; keep S3 links + filenames."""
    if not isinstance(photos, dict):
        return photos
    out: dict[str, Any] = {}
    for view, meta in photos.items():
        if not isinstance(meta, dict):
            continue
        entry = {k: v for k, v in meta.items() if k != "path"}
        out[view] = entry
    return out


# --- bundle ZIP -------------------------------------------------------------

def store_bundle(scan_id: str, filename: str, data: bytes) -> dict[str, Any]:
    """Persist the bundle ZIP, returning a descriptor for the scan item."""
    if SCAN_STORAGE_BACKEND == "s3":
        _require_s3()
        prefix = S3_PHOTO_PREFIX.strip("/")
        key = f"{prefix}/{scan_id}/{filename}"
        _s3_client().put_object(
            Bucket=S3_BUCKET, Key=key, Body=data, ContentType="application/zip"
        )
        url = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{key}"
        logger.info("bundle stored s3://%s/%s", S3_BUCKET, key)
        return {
            "bundle_storage": "s3",
            "bundle_s3_bucket": S3_BUCKET,
            "bundle_s3_key": key,
            "bundle_s3_url": url,
            "bundle_filename": filename,
            "bundle_size_bytes": len(data),
        }
    dest_dir = SCAN_STORAGE_DIR / scan_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    dest.write_bytes(data)
    return {
        "bundle_storage": "disk",
        "bundle_path": str(dest.resolve()),
        "bundle_filename": filename,
        "bundle_size_bytes": len(data),
    }


def open_bundle(scan_doc: dict[str, Any]) -> tuple[BinaryIO | Path, str, int] | None:
    """Return (stream-or-path, filename, size_bytes) for the bundle ZIP, or None."""
    filename = scan_doc.get("bundle_filename") or f"{scan_doc.get('scan_id', 'scan')}.zip"
    size = int(scan_doc.get("bundle_size_bytes", 0) or 0)

    if scan_doc.get("bundle_storage") == "s3" and scan_doc.get("bundle_s3_key"):
        buf = BytesIO()
        _s3_client().download_fileobj(scan_doc["bundle_s3_bucket"], scan_doc["bundle_s3_key"], buf)
        buf.seek(0)
        return buf, filename, size

    path = Path(scan_doc.get("bundle_path", ""))
    return (path, filename, size) if path.is_file() else None
