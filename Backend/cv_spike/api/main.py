"""
Swaya / DSV body-measurement API.

Flows:
  height  — front/back/side + height_cm
  aruco   — photos + 50 mm ArUco marker

Beta:
  POST /v1/scans — persist to MongoDB + downloadable ZIP (OBJ when mesh backend available)

Run:
  cd Backend/cv_spike
  uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    force=True,
)

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.db.mongo import mongo_available, mongo_last_error  # noqa: E402
from api.settings import SCAN_STORAGE_BACKEND  # noqa: E402
from api.forms import (  # noqa: E402
    MeasureMode,
    PreferKind,
    RefKind,
    resolve_measure_request,
    save_upload,
)
from api.routes.scans import router as scans_router  # noqa: E402
from pipeline.measure import smpl_backend  # noqa: E402
from pipeline.measure.measure_engine import measure  # noqa: E402

_ENABLE_QC = os.getenv("ENABLE_QC", "0").strip().lower() in ("1", "true", "yes")

app = FastAPI(
    title="DSV Body Measurement API",
    version="1.2.0",
    description=(
        "Estimate body girths from profile photos.\n\n"
        "**Measure:** `POST /v1/measure` or `/v1/measure/height` (stateless).\n\n"
        "**Beta scans:** `POST /v1/scans` stores results in MongoDB and returns a "
        "downloadable ZIP with `manifest.json`, `measurements.json`, photos, and optional `body.obj`."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(scans_router)

if _ENABLE_QC:
    from api.routes.qc import router as qc_router  # noqa: E402

    app.include_router(qc_router)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "backends": smpl_backend.backend_status(),
        "mongodb": mongo_available(),
        "mongodb_error": mongo_last_error() if not mongo_available() else None,
        "scan_storage": SCAN_STORAGE_BACKEND,
        "qc_enabled": _ENABLE_QC,
    }


@app.post("/v1/measure")
async def measure_body(
    front: UploadFile = File(..., description="Front-facing full-body photo"),
    back: UploadFile = File(..., description="Back-facing full-body photo"),
    side: UploadFile = File(..., description="Side-profile full-body photo"),
    mode: Optional[MeasureMode] = Form(None),
    height_cm: Optional[float] = Form(None),
    weight_kg: Optional[float] = Form(None),
    ref: Optional[RefKind] = Form(None),
    ref_mm: float = Form(50.0),
    tape_in: Optional[str] = Form(None),
    tape_cm: Optional[str] = Form(None),
    prefer: Optional[PreferKind] = Form(None),
) -> dict:
    flow, height_cm, ref, prefer = resolve_measure_request(mode, height_cm, ref, prefer)

    suffix = {
        "front": Path(front.filename or "front.jpg").suffix or ".jpg",
        "back": Path(back.filename or "back.jpg").suffix or ".jpg",
        "side": Path(side.filename or "side.jpg").suffix or ".jpg",
    }

    with tempfile.TemporaryDirectory(prefix="swaya_measure_") as tmp:
        tmp_dir = Path(tmp)
        paths = {view: tmp_dir / f"{view}{suffix[view]}" for view in ("front", "back", "side")}
        await save_upload(front, paths["front"])
        await save_upload(back, paths["back"])
        await save_upload(side, paths["side"])

        try:
            result = measure(
                height_cm=height_cm,
                weight_kg=weight_kg,
                front=paths["front"],
                back=paths["back"],
                side=paths["side"],
                prefer=prefer,
                ref_kind=ref,
                ref_marker_mm=ref_mm,
                tape_in=tape_in,
                tape_cm=tape_cm,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except smpl_backend.BackendUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Measurement failed: {exc}") from exc

    payload = result.to_dict()
    payload["mode"] = flow
    return payload


@app.post("/v1/measure/height")
async def measure_body_height_flow(
    front: UploadFile = File(...),
    back: UploadFile = File(...),
    side: UploadFile = File(...),
    height_cm: float = Form(...),
    weight_kg: Optional[float] = Form(None),
    prefer: Optional[PreferKind] = Form(None),
    tape_in: Optional[str] = Form(None),
    tape_cm: Optional[str] = Form(None),
) -> dict:
    return await measure_body(
        front=front,
        back=back,
        side=side,
        mode="height",
        height_cm=height_cm,
        weight_kg=weight_kg,
        ref=None,
        ref_mm=50.0,
        tape_in=tape_in,
        tape_cm=tape_cm,
        prefer=prefer,
    )
