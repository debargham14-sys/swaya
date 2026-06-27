"""Scan persistence + beta bundle / raw photo download."""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from api.auth import current_uid
from api.db.dynamo import dynamo_available, dynamo_last_error
from api.forms import MeasureMode, PreferKind, RefKind, resolve_measure_request, save_upload
from api.image_prep import prepare_scan_paths
from api.services.scan_service import ScanService, process_uploaded_scan
from api.storage.photo_store import PhotoStorageError
from pipeline.measure import smpl_backend

router = APIRouter(prefix="/v1/scans", tags=["scans"])

GIRTH_LEVELS = ("bust", "underbust", "waist", "hip")


class GroundTruthBody(BaseModel):
    """Tape-measured girths in cm (optional fields — enter what you have)."""

    bust_cm: float | None = Field(None, gt=0, le=250)
    underbust_cm: float | None = Field(None, gt=0, le=250)
    waist_cm: float | None = Field(None, gt=0, le=250)
    hip_cm: float | None = Field(None, gt=0, le=250)

    def to_cm_dict(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for level in GIRTH_LEVELS:
            val = getattr(self, f"{level}_cm")
            if val is not None:
                out[level] = float(val)
        return out


def _require_db() -> None:
    if not dynamo_available():
        raise HTTPException(
            status_code=503,
            detail=f"DynamoDB unavailable: {dynamo_last_error() or 'connection failed'}",
        )


@router.get("")
def list_scans(limit: int = 30, uid: str = Depends(current_uid)) -> dict:
    _require_db()
    return {"scans": ScanService().list_scans(limit=min(limit, 100), user_id=uid)}


@router.get("/{scan_id}")
def get_scan(scan_id: str, uid: str = Depends(current_uid)) -> dict:
    _require_db()
    doc = ScanService().get_scan(scan_id, user_id=uid)
    if not doc:
        raise HTTPException(status_code=404, detail="Scan not found")
    return doc


@router.get("/{scan_id}/bundle")
def download_bundle(scan_id: str, uid: str = Depends(current_uid)):
    _require_db()
    opened = ScanService().open_bundle(scan_id, user_id=uid)
    if not opened:
        raise HTTPException(status_code=404, detail="Bundle not found")
    stream_or_path, filename, _size = opened
    if isinstance(stream_or_path, Path):
        return FileResponse(
            stream_or_path,
            media_type="application/zip",
            filename=filename or f"dsv-scan-{scan_id}.zip",
        )
    return StreamingResponse(
        stream_or_path,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename or f"dsv-scan-{scan_id}.zip"}"'},
    )


@router.get("/{scan_id}/photos/{view}")
def download_photo(scan_id: str, view: str, uid: str = Depends(current_uid)):
    """Download a raw capture photo (front, back, or side) from S3 or local disk."""
    _require_db()
    if view not in ("front", "back", "side"):
        raise HTTPException(status_code=400, detail="view must be front, back, or side")
    opened = ScanService().open_photo(scan_id, view, user_id=uid)
    if not opened:
        raise HTTPException(status_code=404, detail="Photo not found")
    stream, filename, content_type = opened
    return StreamingResponse(
        stream,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("")
async def create_scan(
    front: UploadFile = File(...),
    back: UploadFile = File(...),
    side: UploadFile = File(...),
    mode: Optional[MeasureMode] = Form(None),
    height_cm: Optional[float] = Form(None),
    weight_kg: Optional[float] = Form(None),
    ref: Optional[RefKind] = Form(None),
    ref_mm: float = Form(50.0),
    prefer: Optional[PreferKind] = Form(None),
    subject_label: Optional[str] = Form(
        None, description="Participant name or ID for data collection"
    ),
    collector_id: Optional[str] = Form(
        None, description="Who collected this scan (tester name or device id)"
    ),
    consent_given: Optional[bool] = Form(
        None, description="Subject consented to photo storage and measurement"
    ),
    notes: Optional[str] = Form(None, description="Optional notes for this capture session"),
    uid: str = Depends(current_uid),
) -> dict:
    """
    Upload photos, run measurement, build beta ZIP (manifest + JSON + photos + optional body.obj),
    persist metadata to DynamoDB; photos + bundle to S3 or local disk.
    """
    _require_db()
    flow, height_cm, ref, prefer = resolve_measure_request(mode, height_cm, ref, prefer)

    suffix = {
        "front": Path(front.filename or "front.jpg").suffix or ".jpg",
        "back": Path(back.filename or "back.jpg").suffix or ".jpg",
        "side": Path(side.filename or "side.jpg").suffix or ".jpg",
    }

    with tempfile.TemporaryDirectory(prefix="dsv_scan_") as tmp:
        tmp_dir = Path(tmp)
        paths = {view: tmp_dir / f"{view}{suffix[view]}" for view in ("front", "back", "side")}
        await save_upload(front, paths["front"])
        await save_upload(back, paths["back"])
        await save_upload(side, paths["side"])
        prep_warn = prepare_scan_paths(paths)
        if prep_warn:
            logger.info("scan image prep: %s", "; ".join(prep_warn))

        try:
            t0 = time.perf_counter()
            doc = process_uploaded_scan(
                paths=paths,
                height_cm=height_cm,
                weight_kg=weight_kg,
                mode=flow,
                prefer=prefer,
                ref_kind=ref,
                ref_marker_mm=ref_mm,
                subject_label=subject_label,
                collector_id=collector_id,
                consent_given=consent_given,
                notes=notes,
                user_id=uid,
            )
            logger.info("scan %s processed in %.1fs", doc.get("scan_id"), time.perf_counter() - t0)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except PhotoStorageError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except smpl_backend.BackendUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Scan failed: {exc}") from exc

    return doc


@router.patch("/{scan_id}/ground-truth")
def save_ground_truth(
    scan_id: str, body: GroundTruthBody, uid: str = Depends(current_uid)
) -> dict:
    """Save tape-measured girths for this scan (training / calibration dataset)."""
    _require_db()
    payload = body.to_cm_dict()
    if not payload:
        raise HTTPException(
            status_code=422,
            detail="Provide at least one girth in cm (bust_cm, waist_cm, hip_cm, underbust_cm).",
        )
    doc = ScanService().save_ground_truth(scan_id, payload, user_id=uid)
    if not doc:
        raise HTTPException(status_code=404, detail="Scan not found")
    logger.info("scan %s ground_truth saved: %s", scan_id, list(payload.keys()))
    return doc
