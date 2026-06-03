"""MongoDB client helpers."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from api.settings import MONGODB_DB, MONGODB_URI

_client: Any = None
_last_error: str | None = None


def mongo_available() -> bool:
    try:
        get_db().command("ping")
        return True
    except Exception as exc:  # noqa: BLE001
        global _last_error
        _last_error = str(exc)
        return False


def mongo_last_error() -> str | None:
    return _last_error


@lru_cache(maxsize=1)
def _get_client():
    from pymongo import MongoClient

    return MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)


def get_db():
    return _get_client()[MONGODB_DB]


@lru_cache(maxsize=1)
def get_bucket():
    """GridFS bucket for storing scan bundles + raw capture photos in the cloud."""
    from gridfs import GridFSBucket

    return GridFSBucket(get_db(), bucket_name="scan_files")
