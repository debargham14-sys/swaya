"""API runtime settings (env vars)."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.environ.get("MONGODB_DB", "dsv")
SCAN_STORAGE_DIR = Path(os.environ.get("SCAN_STORAGE_DIR", str(ROOT / "data" / "scans")))
BUNDLE_VERSION = "dsv-beta-1"
# Try SMPL mesh export when building beta bundles (falls back to measurements-only).
# Default off so cloud deploys stay light (no torch/4D-Humans required for data collection).
BUNDLE_TRY_MESH = os.environ.get("BUNDLE_TRY_MESH", "0").strip() not in ("0", "false", "False")

# Where scan bundles + raw photos live: "gridfs" (cloud, default) or "disk" (local dev).
# GridFS keeps every byte inside MongoDB, which is required on hosts with an
# ephemeral filesystem (Render, Railway, Fly) and for cloud data collection.
SCAN_STORAGE_BACKEND = os.environ.get("SCAN_STORAGE_BACKEND", "gridfs").strip().lower()
