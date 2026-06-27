"""Fit assistant API — garment suggestions from measurements."""

from __future__ import annotations  # noqa: TC003 — pydantic on py3.9

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends

from pydantic import BaseModel, Field

from api.auth import current_uid
from api.db.dynamo import dynamo_available
from api.services.assistant_service import chat_reply, llm_available, suggest_garments

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/assistant", tags=["assistant"])


def _user_context(uid: str) -> tuple[list, list]:
    """The caller's orders + personas for the assistant to reason over.

    Best-effort: if Dynamo is unreachable or the caller is anonymous, returns
    empty lists so the assistant still works (just without order awareness).
    """
    if not uid or not dynamo_available():
        return [], []
    orders: list = []
    personas: list = []
    try:
        from api.db.orders import OrderRepository

        orders = OrderRepository().list(uid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("assistant: could not load orders: %s", exc)
    try:
        from api.db.personas import PersonaRepository

        personas = PersonaRepository().list(uid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("assistant: could not load personas: %s", exc)
    return orders, personas


class MeasurementsContext(BaseModel):
    girths_cm: Dict[str, float] = Field(default_factory=dict)
    girths_in: Dict[str, float] = Field(default_factory=dict)
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    confidence: Optional[float] = None
    calibration_profile: Optional[str] = None


class SuggestRequest(BaseModel):
    measurements: MeasurementsContext
    calibrated: bool = False
    context: Optional[str] = None
    gender: str = "female"
    garment: Optional[str] = None


class ChatMessage(BaseModel):
    role: str
    text: str


class ChatRequest(BaseModel):
    measurements: MeasurementsContext
    message: str = Field(..., min_length=1, max_length=2000)
    history: List[ChatMessage] = Field(default_factory=list)
    gender: str = "female"
    garment: Optional[str] = None


@router.get("/status")
def assistant_status() -> dict[str, Any]:
    return {"llm_available": llm_available(), "fallback": "rules"}


@router.post("/suggest")
async def suggest(
    body: SuggestRequest, uid: str = Depends(current_uid)
) -> dict[str, Any]:
    orders, personas = _user_context(uid)
    return await suggest_garments(
        body.measurements.model_dump(exclude_none=True),
        calibrated=body.calibrated,
        context=body.context,
        gender=body.gender,
        garment=body.garment,
        orders=orders,
        personas=personas,
    )


@router.post("/chat")
async def chat(
    body: ChatRequest, uid: str = Depends(current_uid)
) -> dict[str, Any]:
    orders, personas = _user_context(uid)
    hist = [{"role": m.role, "text": m.text} for m in body.history]
    return await chat_reply(
        body.measurements.model_dump(exclude_none=True),
        body.message,
        history=hist,
        gender=body.gender,
        garment=body.garment,
        orders=orders,
        personas=personas,
    )
