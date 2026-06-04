"""Global tape calibration profile (learned from ground truth)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.db.mongo import mongo_available, mongo_last_error
from api.services.calibration_service import clear_global_profile, get_global_profile

router = APIRouter(prefix="/v1/calibration", tags=["calibration"])


def _require_mongo() -> None:
    if not mongo_available():
        raise HTTPException(
            status_code=503,
            detail=f"MongoDB unavailable: {mongo_last_error() or 'not configured'}",
        )


@router.get("/global")
def get_global_calibration() -> dict:
    """Return the active global calibration profile, if any."""
    _require_mongo()
    profile = get_global_profile()
    if not profile:
        return {"active": False}
    return {"active": True, "profile": profile.to_dict()}


@router.delete("/global")
def reset_global_calibration() -> dict:
    """Clear learned calibration (use after bad scans polluted the profile)."""
    _require_mongo()
    cleared = clear_global_profile()
    return {"cleared": cleared}
