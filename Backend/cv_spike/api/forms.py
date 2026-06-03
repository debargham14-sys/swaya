"""Shared request parsing for measure + scan endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from fastapi import HTTPException, UploadFile

RefKind = Literal["aruco", "card", "a4"]
MeasureMode = Literal["height", "aruco"]
PreferKind = Literal["auto", "obj", "four_d_humans", "smplx", "photo"]
QcTier = Literal["couture", "bespoke", "express"]


def resolve_qc_request(
    order_id: Optional[str], spec: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    """Validate that a QC request carries either inline spec JSON or an order_id."""
    if not order_id and not spec:
        raise HTTPException(
            status_code=422,
            detail="Provide spec (inline JSON) or order_id to load the order spec.",
        )
    return order_id, spec


async def save_upload(upload: UploadFile, dest: Path) -> None:
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail=f"Empty upload: {upload.filename}")
    dest.write_bytes(data)


def resolve_measure_request(
    mode: Optional[MeasureMode],
    height_cm: Optional[float],
    ref: Optional[RefKind],
    prefer: Optional[PreferKind],
) -> tuple[MeasureMode, Optional[float], Optional[RefKind], PreferKind]:
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
        return mode, height_cm, ref, resolved_prefer

    if ref is None:
        ref = "aruco"
    resolved_prefer = prefer or "photo"
    return mode, height_cm, ref, resolved_prefer
