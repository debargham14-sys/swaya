"""Scan persistence + beta bundle / raw photo download."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from api.db.mongo import mongo_available, mongo_last_error
from api.forms import MeasureMode, PreferKind, RefKind, resolve_measure_request, save_upload
from api.image_prep import downscale_scan_paths
from api.services.scan_service import ScanService, process_uploaded_scan
from pipeline.measure import smpl_backend

router = APIRouter(prefix="/v1/scans", tags=["scans"])


def _require_mongo() -> None:
    if not mongo_available():
        raise HTTPException(
            status_code=503,
            detail=f"MongoDB unavailable: {mongo_last_error() or 'connection failed'}",
        )


@router.get("")
def list_scans(limit: int = 30) -> dict:
    _require_mongo()
    return {"scans": ScanService().list_scans(limit=min(limit, 100))}


@router.get("/{scan_id}")
def get_scan(scan_id: str) -> dict:
    _require_mongo()
    doc = ScanService().get_scan(scan_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Scan not found")
    return doc


@router.get("/{scan_id}/bundle")
def download_bundle(scan_id: str):
    _require_mongo()
    opened = ScanService().open_bundle(scan_id)
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
def download_photo(scan_id: str, view: str):
    """Download a raw capture photo (front, back, or side) from GridFS."""
    _require_mongo()
    if view not in ("front", "back", "side"):
        raise HTTPException(status_code=400, detail="view must be front, back, or side")
    opened = ScanService().open_photo(scan_id, view)
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
) -> dict:
    """
    Upload photos, run measurement, build beta ZIP (manifest + JSON + photos + optional body.obj),
    persist metadata + raw photos + bundle to MongoDB (GridFS by default).
    """
    _require_mongo()
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
        downscale_scan_paths(paths)

        try:
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
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except smpl_backend.BackendUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Scan failed: {exc}") from exc

    return doc
