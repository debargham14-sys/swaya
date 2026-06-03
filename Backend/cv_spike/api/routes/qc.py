"""QC (quality-check) endpoint.

Run the QC pipeline on a flat-lay photo of a finished blouse inside the
standardized QC framework. The spec sheet comes from inline JSON or an
``order_id`` lookup (mirroring the cutting-region QR-code workflow).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from api.forms import QcTier, resolve_qc_request, save_upload
from pipeline.qc.qc_engine import run_qc
from pipeline.qc.spec import load_spec

router = APIRouter(prefix="/v1/qc", tags=["qc"])


@router.post("")
async def quality_check(
    front: UploadFile = File(..., description="Flat-lay blouse-on-framework photo (front)"),
    back: Optional[UploadFile] = File(None, description="Optional back flat-lay photo"),
    hanging: Optional[UploadFile] = File(None, description="Optional hanging photo (drape checks)"),
    order_id: Optional[str] = Form(None, description="Order id resolved via OrderRepository"),
    spec: Optional[str] = Form(None, description="Inline order spec JSON"),
    tier: Optional[QcTier] = Form(None, description="Override the spec's tolerance tier"),
) -> dict:
    order_id, spec = resolve_qc_request(order_id, spec)

    try:
        order_spec = load_spec(order_id=order_id, spec_json=spec)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if tier:
        order_spec.tier = tier

    suffix = Path(front.filename or "front.jpg").suffix or ".jpg"
    with tempfile.TemporaryDirectory(prefix="swaya_qc_") as tmp:
        front_path = Path(tmp) / f"front{suffix}"
        await save_upload(front, front_path)
        try:
            result = run_qc(front_path, order_spec)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"QC failed: {exc}") from exc

    return result.to_dict()
