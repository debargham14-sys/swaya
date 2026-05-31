"""
Swaya body-measurement API.

Two supported capture flows:

  height  — front/back/side photos + subject height (cm); 4D-Humans mesh by default
  aruco   — same photos + 50 mm ArUco at chest; photo silhouettes by default

Run:
  cd Backend/cv_spike
  uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import smpl_backend  # noqa: E402
from pipeline.measure_engine import measure  # noqa: E402

app = FastAPI(
    title="Swaya Body Measurement API",
    version="1.1.0",
    description=(
        "Estimate body girths from front, back, and side profile photos.\n\n"
        "**Height flow:** send `mode=height`, `height_cm` → photo silhouettes (default; best with loose clothing). "
        "Use `prefer=four_d_humans` for SMPL mesh (needs fitted clothing).\n\n"
        "**ArUco flow:** send `mode=aruco` (or omit height) with a 50 mm chest marker → "
        "photo silhouettes (default)."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

RefKind = Literal["aruco", "card", "a4"]
MeasureMode = Literal["height", "aruco"]
PreferKind = Literal["auto", "obj", "four_d_humans", "smplx", "photo"]


async def _save_upload(upload: UploadFile, dest: Path) -> None:
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail=f"Empty upload: {upload.filename}")
    dest.write_bytes(data)


def _resolve_request(
    mode: MeasureMode | None,
    height_cm: float | None,
    ref: RefKind | None,
    prefer: PreferKind | None,
) -> tuple[MeasureMode, float | None, RefKind | None, PreferKind]:
    """Pick flow defaults: height → 4D-Humans; aruco → photo silhouettes."""
    if mode is None:
        if height_cm is not None:
            mode = "height"
        elif ref is not None:
            mode = "aruco"
        else:
            raise HTTPException(
                status_code=422,
                detail="Set mode=height with height_cm, or mode=aruco with ref=aruco.",
            )

    if mode == "height":
        if height_cm is None:
            raise HTTPException(status_code=422, detail="mode=height requires height_cm.")
        resolved_prefer: PreferKind = prefer or "photo"
        # Scale from stature; ref only if client also sends one
        return mode, height_cm, ref, resolved_prefer

    if ref is None:
        ref = "aruco"
    resolved_prefer = prefer or "photo"
    return mode, height_cm, ref, resolved_prefer


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "backends": smpl_backend.backend_status()}


@app.post("/v1/measure")
async def measure_body(
    front: UploadFile = File(..., description="Front-facing full-body photo"),
    back: UploadFile = File(..., description="Back-facing full-body photo"),
    side: UploadFile = File(..., description="Side-profile full-body photo"),
    mode: Optional[MeasureMode] = Form(
        None,
        description="height: send height_cm (4D-Humans default). aruco: chest marker (photo default).",
    ),
    height_cm: Optional[float] = Form(None, description="Subject height in cm (required for mode=height)"),
    weight_kg: Optional[float] = Form(None, description="Subject weight in kg (optional, for BMI)"),
    ref: Optional[RefKind] = Form(
        None,
        description="Scale reference in frame (required for mode=aruco unless height_cm is set)",
    ),
    ref_mm: float = Form(50.0, description="Printed ArUco marker side length in mm"),
    tape_in: Optional[str] = Form(None, description="Tape anchors in inches, e.g. bust=44,waist=38"),
    tape_cm: Optional[str] = Form(None, description="Tape anchors in cm"),
    prefer: Optional[PreferKind] = Form(
        None,
        description="Default: photo (height flow) or photo (aruco flow). four_d_humans needs fitted clothes.",
    ),
) -> dict:
    flow, height_cm, ref, prefer = _resolve_request(mode, height_cm, ref, prefer)

    suffix = {
        "front": Path(front.filename or "front.jpg").suffix or ".jpg",
        "back": Path(back.filename or "back.jpg").suffix or ".jpg",
        "side": Path(side.filename or "side.jpg").suffix or ".jpg",
    }

    with tempfile.TemporaryDirectory(prefix="swaya_measure_") as tmp:
        tmp_dir = Path(tmp)
        paths = {
            view: tmp_dir / f"{view}{suffix[view]}"
            for view in ("front", "back", "side")
        }
        await _save_upload(front, paths["front"])
        await _save_upload(back, paths["back"])
        await _save_upload(side, paths["side"])

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
    height_cm: float = Form(..., description="Subject height in cm"),
    weight_kg: Optional[float] = Form(None),
    prefer: Optional[PreferKind] = Form(None, description="Default: four_d_humans"),
    tape_in: Optional[str] = Form(None),
    tape_cm: Optional[str] = Form(None),
) -> dict:
    """Convenience endpoint: height + weight + 3 photos → 4D-Humans mesh (default)."""
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
