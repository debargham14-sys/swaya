"""User profile sync — store the signed-in user's details in DynamoDB."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import current_uid, require_user
from api.db.dynamo import dynamo_available, dynamo_last_error
from api.db.users import UserRepository

router = APIRouter(prefix="/v1/users", tags=["users"])


def _require_db() -> None:
    if not dynamo_available():
        raise HTTPException(
            status_code=503,
            detail=f"DynamoDB unavailable: {dynamo_last_error() or 'not configured'}",
        )


class UserBody(BaseModel):
    email: str | None = None
    name: str | None = None
    phone: str | None = None


@router.post("/me")
def sync_me(body: UserBody | None = None, claims: dict = Depends(require_user)) -> dict:
    """Upsert the caller's user record. Falls back to the token's claims for any
    field the client doesn't send (email/name/phone are in the Firebase token)."""
    _require_db()
    uid = str(claims.get("uid") or claims.get("user_id") or "")
    if not uid:
        raise HTTPException(status_code=401, detail="No user id in token.")
    body = body or UserBody()
    return UserRepository().upsert(
        uid,
        email=body.email or claims.get("email"),
        name=body.name or claims.get("name"),
        phone=body.phone or claims.get("phone_number"),
    )


@router.get("/me")
def get_me(uid: str = Depends(current_uid)) -> dict:
    """Return the caller's stored user record."""
    _require_db()
    doc = UserRepository().get(uid)
    if not doc:
        raise HTTPException(status_code=404, detail="User record not found.")
    return doc
