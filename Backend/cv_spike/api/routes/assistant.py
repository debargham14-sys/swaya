"""Fit assistant API — garment suggestions from measurements."""

from __future__ import annotations  # noqa: TC003 — pydantic on py3.9

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.services.assistant_service import chat_reply, llm_available, suggest_garments

router = APIRouter(prefix="/v1/assistant", tags=["assistant"])


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


class ChatMessage(BaseModel):
    role: str
    text: str


class ChatRequest(BaseModel):
    measurements: MeasurementsContext
    message: str = Field(..., min_length=1, max_length=2000)
    history: List[ChatMessage] = Field(default_factory=list)


@router.get("/status")
def assistant_status() -> dict[str, Any]:
    return {"llm_available": llm_available(), "fallback": "rules"}


@router.post("/suggest")
async def suggest(body: SuggestRequest) -> dict[str, Any]:
    return await suggest_garments(
        body.measurements.model_dump(exclude_none=True),
        calibrated=body.calibrated,
        context=body.context,
    )


@router.post("/chat")
async def chat(body: ChatRequest) -> dict[str, Any]:
    hist = [{"role": m.role, "text": m.text} for m in body.history]
    return await chat_reply(
        body.measurements.model_dump(exclude_none=True),
        body.message,
        history=hist,
    )
