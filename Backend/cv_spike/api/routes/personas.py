"""Personas (named profiles + their blouse measurements), scoped to the caller."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import current_uid
from api.db.dynamo import dynamo_available, dynamo_last_error
from api.db.personas import PersonaRepository

router = APIRouter(prefix="/v1/personas", tags=["personas"])


def _require_db() -> None:
    if not dynamo_available():
        raise HTTPException(
            status_code=503,
            detail=f"DynamoDB unavailable: {dynamo_last_error() or 'not configured'}",
        )


class PersonaBody(BaseModel):
    name: str
    label: str | None = None
    # field-key -> centimetres (kBlouseFields on the app side).
    measurements: dict[str, float] = Field(default_factory=dict)


@router.get("")
def list_personas(uid: str = Depends(current_uid)) -> dict:
    """All of the caller's personas, newest first."""
    _require_db()
    return {"personas": PersonaRepository().list(uid)}


@router.put("/{persona_id}")
def upsert_persona(
    persona_id: str, body: PersonaBody, uid: str = Depends(current_uid)
) -> dict:
    """Create or replace a persona (the app supplies a stable persona_id)."""
    _require_db()
    return PersonaRepository().upsert(
        uid,
        persona_id,
        name=body.name,
        label=body.label,
        measurements=body.measurements,
    )


@router.delete("/{persona_id}")
def delete_persona(persona_id: str, uid: str = Depends(current_uid)) -> dict:
    """Delete one of the caller's personas."""
    _require_db()
    if not PersonaRepository().delete(uid, persona_id):
        raise HTTPException(status_code=404, detail="Persona not found.")
    return {"deleted": True}
