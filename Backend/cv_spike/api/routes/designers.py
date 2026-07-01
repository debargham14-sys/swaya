"""Designers/tailors — browseable profiles + self-registration, ratings.

Any signed-in user can browse the directory (``GET ""``) and a single profile.
The caller manages only their *own* profile via ``/me``. Registering a profile
is what turns a user into a designer (also flips ``users.role`` to ``designer``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import current_uid
from api.db.designers import DesignerRepository
from api.db.dynamo import dynamo_available, dynamo_last_error
from api.db.users import UserRepository

router = APIRouter(prefix="/v1/designers", tags=["designers"])


def _require_db() -> None:
    if not dynamo_available():
        raise HTTPException(
            status_code=503,
            detail=f"DynamoDB unavailable: {dynamo_last_error() or 'not configured'}",
        )


class DesignerProfile(BaseModel):
    name: str
    bio: str | None = None
    specialties: list[str] = Field(default_factory=list)
    location: str | None = None
    years_experience: int | None = None
    price_range: str | None = None
    photo_url: str | None = None
    available: bool = True


class RatingBody(BaseModel):
    stars: float = Field(ge=1, le=5)


@router.get("")
def list_designers(
    available: bool = Query(False), uid: str = Depends(current_uid)
) -> dict:
    """The designer directory. ``?available=1`` filters to available designers."""
    _require_db()
    return {"designers": DesignerRepository().list(available_only=available)}


@router.get("/me")
def my_designer_profile(uid: str = Depends(current_uid)) -> dict:
    """The caller's own designer profile (``{designer: null}`` if not a designer)."""
    _require_db()
    return {"designer": DesignerRepository().get_client(uid)}


@router.post("/me")
def upsert_my_profile(body: DesignerProfile, uid: str = Depends(current_uid)) -> dict:
    """Register as / update being a designer. Idempotent."""
    _require_db()
    profile = DesignerRepository().upsert(uid, body.model_dump())
    UserRepository().set_role(uid, "designer")
    return profile


@router.post("/seed")
def seed_designers(uid: str = Depends(current_uid)) -> dict:
    """Load the demo designer set (idempotent) so the directory isn't empty."""
    _require_db()
    return {"designers": DesignerRepository().seed_samples()}


@router.get("/{designer_id}")
def get_designer(designer_id: str, uid: str = Depends(current_uid)) -> dict:
    _require_db()
    doc = DesignerRepository().get_client(designer_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Designer not found.")
    return doc


@router.post("/{designer_id}/rating")
def rate_designer(
    designer_id: str, body: RatingBody, uid: str = Depends(current_uid)
) -> dict:
    _require_db()
    doc = DesignerRepository().add_rating(designer_id, body.stars)
    if not doc:
        raise HTTPException(status_code=404, detail="Designer not found.")
    return doc
