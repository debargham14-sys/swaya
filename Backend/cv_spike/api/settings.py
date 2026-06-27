"""API runtime settings (env vars)."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# --- DynamoDB (scan + calibration metadata) ---------------------------------
# Replaces MongoDB. Physical tables are named "{DYNAMO_TABLE_PREFIX}_{logical}":
#   dsv_scans, dsv_calibration, dsv_vest_scans, dsv_vest_calibration.
# DYNAMO_ENDPOINT_URL points at DynamoDB Local / moto for offline dev + tests;
# leave it empty to use the real AWS endpoint for AWS_REGION.
DYNAMO_TABLE_PREFIX = os.environ.get("DYNAMO_TABLE_PREFIX", "dsv").strip()
DYNAMO_ENDPOINT_URL = os.environ.get("DYNAMO_ENDPOINT_URL", "").strip()

SCAN_STORAGE_DIR = Path(os.environ.get("SCAN_STORAGE_DIR", str(ROOT / "data" / "scans")))
BUNDLE_VERSION = "dsv-beta-1"
# Try SMPL mesh export when building beta bundles (falls back to measurements-only).
# Default off so cloud deploys stay light (no torch/4D-Humans required for data collection).
BUNDLE_TRY_MESH = os.environ.get("BUNDLE_TRY_MESH", "0").strip() not in ("0", "false", "False")


def _blob_backend(raw: str) -> str:
    """Normalize a blob-storage backend, mapping the legacy 'gridfs' value to 's3'.

    DynamoDB items are capped at 400 KB, so binaries (bundle ZIPs, photos) never
    live in the DB. Valid backends: 's3' (cloud) or 'disk' (local dev).
    """
    val = (raw or "").strip().lower()
    return "s3" if val == "gridfs" else (val or "disk")


# Where scan bundles + raw photos live: "s3" (cloud) or "disk" (local dev).
SCAN_STORAGE_BACKEND = _blob_backend(os.environ.get("SCAN_STORAGE_BACKEND", "disk"))
PHOTO_STORAGE = _blob_backend(os.environ.get("PHOTO_STORAGE", "disk"))
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_PHOTO_PREFIX = os.environ.get("S3_PHOTO_PREFIX", "dsv/scans")

# --- Firebase Authentication ------------------------------------------------
# The mobile app authenticates with Firebase; the API verifies the Firebase ID
# token (a JWT) on protected routes. Provide credentials one of three ways:
#   1. FIREBASE_SERVICE_ACCOUNT_JSON  — the service-account JSON, inline (best
#      for Render/Railway secrets).
#   2. GOOGLE_APPLICATION_CREDENTIALS — path to a service-account JSON file.
#   3. FIREBASE_PROJECT_ID            — use Application Default Credentials.
# When none are set, auth is DISABLED and routes run unauthenticated (local dev),
# mirroring how Mongo degrades gracefully.
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "").strip()
FIREBASE_SERVICE_ACCOUNT_JSON = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
# Hard-require a verified user on protected routes even in dev (set to "1").
AUTH_REQUIRED = os.environ.get("AUTH_REQUIRED", "0").strip() not in ("0", "false", "False", "")
