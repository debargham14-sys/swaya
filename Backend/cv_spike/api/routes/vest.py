"""
Vest ChArUco measurement (BETA) — tailor data-collection endpoints.

POST   /v1/vest                      measure a front (+optional side) vest capture and store it
GET    /v1/vest                      list recent vest scans
GET    /v1/vest/{scan_id}            one scan's metadata + measurement
PATCH  /v1/vest/{scan_id}/ground-truth   attach tape-measured girths (inches)

Marker scheme + algorithm: pipeline/measure/vest_charuco.py. Front bust/waist/hip
only are trusted today; results carry a confidence + warnings and are flagged beta.
"""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from api.db.mongo import mongo_available, mongo_last_error
from api.forms import save_upload
from api.image_prep import prepare_vest_paths
from api.services.vest_service import (
    get_vest_scan,
    list_vest_scans,
    process_vest_scan,
    save_vest_ground_truth,
)
from api.storage.photo_store import PhotoStorageError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/vest", tags=["vest (beta)"])

_VEST_VIEWS = ("front", "side_left", "side_right")


class VestGroundTruthIn(BaseModel):
    """Tape-measured girths in inches (tailor units). Enter what you have."""

    bust_in: float | None = Field(None, gt=0, le=100)
    waist_in: float | None = Field(None, gt=0, le=100)
    hip_in: float | None = Field(None, gt=0, le=100)
    height_cm: float | None = Field(None, gt=0, le=250)

    def to_dict(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.model_dump().items() if v is not None}


def _require_mongo() -> None:
    if not mongo_available():
        raise HTTPException(
            status_code=503,
            detail=f"MongoDB unavailable: {mongo_last_error() or 'connection failed'}",
        )


@router.post("")
async def create_vest_scan(
    front: UploadFile = File(..., description="Front worn-vest photo (required)"),
    back: Optional[UploadFile] = File(None, description="Back worn-vest photo (optional)"),
    side_left: Optional[UploadFile] = File(None, description="Left side profile (optional)"),
    side_right: Optional[UploadFile] = File(None, description="Right side profile (optional)"),
    subject_label: Optional[str] = Form(None, description="Participant name or ID"),
    collector_id: Optional[str] = Form(None, description="Tailor / collector name or device id"),
    consent_given: Optional[bool] = Form(None, description="Subject consented to storage"),
    notes: Optional[str] = Form(None),
    bust_in: Optional[float] = Form(None, description="Tape bust (in), if measured"),
    waist_in: Optional[float] = Form(None, description="Tape waist (in), if measured"),
    hip_in: Optional[float] = Form(None, description="Tape hip (in), if measured"),
    height_cm: Optional[float] = Form(None, description="Subject height (cm), if known"),
) -> dict:
    """
    Measure a ChArUco vest capture and store it for data collection.

    Returns the beta measurement (front bust/waist/hip girths + confidence +
    warnings). Works without MongoDB (measurement only, ``stored=false``).
    """
    uploads = {"front": front, "back": back, "side_left": side_left, "side_right": side_right}
    gt = VestGroundTruthIn(bust_in=bust_in, waist_in=waist_in, hip_in=hip_in, height_cm=height_cm)

    with tempfile.TemporaryDirectory(prefix="dsv_vest_") as tmp:
        tmp_dir = Path(tmp)
        paths: dict[str, Path] = {}
        for view, up in uploads.items():
            if up is None:
                continue
            suffix = Path(up.filename or f"{view}.jpg").suffix or ".jpg"
            dest = tmp_dir / f"{view}{suffix}"
            await save_upload(up, dest)
            paths[view] = dest

        if "front" not in paths:
            raise HTTPException(status_code=400, detail="front photo is required")

        prep_warn = prepare_vest_paths(paths)
        if prep_warn:
            logger.info("vest image prep: %s", "; ".join(prep_warn))

        try:
            t0 = time.perf_counter()
            doc = process_vest_scan(
                paths=paths,
                subject_label=subject_label,
                collector_id=collector_id,
                consent_given=consent_given,
                notes=notes,
                ground_truth_in=gt.to_dict() or None,
            )
            logger.info(
                "vest scan %s in %.1fs (stored=%s)",
                doc.get("scan_id"), time.perf_counter() - t0, doc.get("stored"),
            )
        except PhotoStorageError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Vest measurement failed: {exc}") from exc

    return doc


@router.get("")
def list_scans(limit: int = 30) -> dict:
    _require_mongo()
    return {"scans": list_vest_scans(limit=limit)}


# NOTE: /calibration must be declared before /{scan_id} or the path param eats it.
@router.get("/calibration")
def get_calibration() -> dict:
    """Current factor + what re-fitting from accumulated ground truth would suggest."""
    _require_mongo()
    from api.services.vest_calibration import recompute_calibration

    return recompute_calibration(apply=False)


@router.post("/calibration/recompute")
def recompute_calibration_endpoint(apply: bool = False) -> dict:
    """Re-fit the calibration factor from ground-truth pairs; pass apply=true to persist it."""
    _require_mongo()
    from api.services.vest_calibration import recompute_calibration

    return recompute_calibration(apply=apply)


@router.get("/{scan_id}")
def get_scan(scan_id: str) -> dict:
    _require_mongo()
    doc = get_vest_scan(scan_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Vest scan not found")
    return doc


@router.patch("/{scan_id}/ground-truth")
def patch_ground_truth(scan_id: str, body: VestGroundTruthIn) -> dict:
    _require_mongo()
    payload = body.to_dict()
    if not payload:
        raise HTTPException(status_code=422, detail="Provide at least one of bust_in/waist_in/hip_in/height_cm")
    doc = save_vest_ground_truth(scan_id, payload)
    if not doc:
        raise HTTPException(status_code=404, detail="Vest scan not found")
    logger.info("vest scan %s ground_truth saved: %s", scan_id, list(payload.keys()))
    return doc
