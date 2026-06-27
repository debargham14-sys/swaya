"""Fit assistant: LLM garment suggestions from body measurements."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# LLM backend selection (in priority order):
#   1. Amazon Bedrock — set BEDROCK_MODEL_ID (e.g. "amazon.nova-lite-v1:0").
#      Called via the instance IAM role — no API key. The cheapest option.
#   2. Anthropic first-party API — set ANTHROPIC_API_KEY.
#   3. Rule-based fallback — neither configured.
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "").strip()
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1").strip()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

_bedrock_client = None


def _get_bedrock():
    """Lazily create a cached bedrock-runtime client (uses the instance role)."""
    global _bedrock_client
    if _bedrock_client is None:
        import boto3

        _bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    return _bedrock_client

# Gender-appropriate garment vocabularies used to steer the LLM and the
# rule-based fallback. Female is the original India-centric set; male adds
# kurta/shirt/sherwani/etc. so male personas aren't pushed into a blouse.
_GARMENTS_BY_GENDER = {
    "female": ["blouse", "saree blouse", "kurta", "lehenga", "salwar suit", "dress"],
    "male": ["kurta", "shirt", "sherwani", "nehru jacket", "trousers"],
}


def _suggest_system(gender: str, garment: str | None) -> str:
    gender = (gender or "female").lower()
    garments = ", ".join(_GARMENTS_BY_GENDER.get(gender, _GARMENTS_BY_GENDER["female"]))
    focus = (
        f"The user is designing a {garment}, so lead with that garment.\n"
        if garment
        else ""
    )
    return (
        "You are a fit assistant for Indian tailoring and ready-to-wear.\n"
        f"The wearer is {gender}. Only suggest garments appropriate for them, "
        f"choosing from: {garments}.\n"
        f"{focus}"
        "Given body girth measurements in cm, suggest 2–3 specific garment types "
        "with practical cutting/ease notes for a tailor or shopper.\n"
        "When the user's saved people (personas) or past orders are provided below, "
        "use them: answer questions about their orders, avoid re-suggesting something "
        "they already ordered, and tailor advice to the right person.\n"
        "Be concise (under 180 words). Use bullet points. Mention cm values from the scan.\n"
        "If measurements look incomplete, say what else is needed."
    )


def llm_available() -> bool:
    return bool(BEDROCK_MODEL_ID or ANTHROPIC_API_KEY)


def _fmt_measurements(m: dict[str, Any]) -> str:
    girths = m.get("girths_cm") or {}
    parts = [f"{k}: {v} cm" for k, v in girths.items() if v is not None]
    height = m.get("height_cm")
    if height:
        parts.insert(0, f"height: {height} cm")
    calibrated = m.get("calibration_profile")
    if calibrated:
        parts.append(f"(calibrated: {calibrated})")
    return ", ".join(parts) if parts else "no girths available"


def _fmt_orders(orders: list[dict[str, Any]] | None) -> str:
    """Compact summary of the user's recent orders for the LLM context."""
    if not orders:
        return ""
    lines = []
    for o in orders[:10]:
        oid = o.get("id", "?")
        garment = o.get("garment") or "garment"
        status = o.get("status") or o.get("category") or "—"
        placed = o.get("placed_on")
        line = f"- {oid}: {garment} ({status}"
        line += f", placed {placed})" if placed else ")"
        lines.append(line)
    return "\n".join(lines)


def _fmt_personas(personas: list[dict[str, Any]] | None) -> str:
    """Compact summary of the user's saved people + key measurements."""
    if not personas:
        return ""
    lines = []
    for p in personas[:10]:
        name = p.get("name") or "Unnamed"
        gender = p.get("gender") or "female"
        meas = p.get("measurements") or {}
        keys = [k for k in ("chest", "bust", "waist", "hip") if meas.get(k)]
        bits = ", ".join(f"{k} {meas[k]:.0f}cm" for k in keys)
        lines.append(f"- {name} ({gender}){f': {bits}' if bits else ''}")
    return "\n".join(lines)


def _context_block(orders: list | None, personas: list | None) -> str:
    """Build the 'what the assistant knows about this user' block, if any."""
    parts = []
    p = _fmt_personas(personas)
    if p:
        parts.append("The user's saved people (personas):\n" + p)
    o = _fmt_orders(orders)
    if o:
        parts.append("The user's recent orders:\n" + o)
    return "\n\n".join(parts)


def _chat_system(gender: str, garment: str | None) -> str:
    """Conversational persona for the interactive assistant (vs the one-shot
    suggestion prompt). Chats naturally and only gives specs when asked."""
    gender = (gender or "female").lower()
    garments = ", ".join(_GARMENTS_BY_GENDER.get(gender, _GARMENTS_BY_GENDER["female"]))
    focus = f"They are currently looking at a {garment}. " if garment else ""
    return (
        "You are Swaya's friendly clothing fit and design assistant for Indian "
        f"tailoring and ready-to-wear. The customer is {gender}. {focus}\n"
        "Chat naturally and conversationally. Greet warmly, keep small talk brief, "
        "and answer what the user actually asks.\n"
        "You can help with garment ideas, fit and sizing, fabrics, colours and "
        "styling, and questions about the user's saved people and past orders "
        "(provided below when available).\n"
        f"When suggesting garments, only suggest ones appropriate for a {gender} "
        f"customer, choosing from: {garments}.\n"
        "Only give specific measurements or ease numbers when the user asks about "
        "fit or sizing — do NOT dump garment specs in response to a greeting or a "
        "general question.\n"
        "Keep replies short (1–4 sentences) and warm. Use bullet points only when "
        "listing a few options."
    )


def _rule_suggest(
    measurements: dict[str, Any], *, calibrated: bool, gender: str = "female"
) -> dict[str, Any]:
    gender = (gender or "female").lower()
    g = measurements.get("girths_cm") or {}
    chest = g.get("bust") if gender == "female" else (g.get("chest") or g.get("bust"))
    waist = g.get("waist")
    hip = g.get("hip")
    lines: list[str] = []

    if calibrated:
        lines.append("Measurements were recalibrated with your tape values — suggestions below use the updated numbers.")

    if gender == "male":
        if chest is not None:
            lines.append(
                f"• Kurta / shirt: cut chest {round(chest + 10)}–{round(chest + 14)} cm "
                f"(10–14 cm ease over {chest:.1f} cm)."
            )
            lines.append(
                f"• Sherwani / Nehru jacket: structured chest ~{round(chest + 8)} cm with a clean shoulder line."
            )
        if waist is not None:
            lines.append(
                f"• Trousers / pyjama: waist {waist:.1f} cm — add 1–2 cm ease at the waistband."
            )
        garments = ["kurta", "shirt", "sherwani"] if chest else []
    else:
        if chest is not None:
            ease_lo = round(chest + 5)
            ease_hi = round(chest + 8)
            lines.append(
                f"• Fitted blouse / saree blouse: cut bust {ease_lo}–{ease_hi} cm "
                f"(5–8 cm ease over {chest:.1f} cm)."
            )
            lines.append(
                f"• Structured kurta: bust panel ~{round(chest + 10)} cm for comfortable movement."
            )
        if waist is not None:
            lines.append(
                f"• High-waist lehenga / skirt: waist {waist:.1f} cm — add 2–3 cm ease for sitting."
            )
        if hip is not None:
            lines.append(
                f"• Lehenga bottom / palazzo: hip {hip:.1f} cm — allow 4–6 cm ease at hip line."
            )
        garments = ["blouse", "kurta", "lehenga"] if chest else []

    if not lines:
        lines.append(
            "Save at least chest/bust or waist tape measurements to unlock tailored garment suggestions."
        )

    return {
        "suggestions": "\n".join(lines),
        "source": "rules",
        "garments": garments,
    }


def _rule_chat(
    measurements: dict[str, Any],
    user_message: str,
    orders: list[dict[str, Any]] | None = None,
) -> str:
    lower = user_message.lower().strip()
    g = measurements.get("girths_cm") or {}
    bust, waist, hip = g.get("bust"), g.get("waist"), g.get("hip")

    if any(lower == w or lower.startswith(w) for w in ("hi", "hello", "hey", "namaste")):
        return ("Hi! I'm your Swaya design assistant. I can suggest garments, help "
                "with fit and fabrics, or answer questions about your orders. What "
                "would you like?")

    if any(w in lower for w in ("what can you", "help", "who are you")):
        return ("I can suggest garments for your measurements, advise on fit, ease, "
                "fabrics and styling, and tell you about your saved orders. Ask away!")

    if any(w in lower for w in ("order", "ordered", "delivery", "status", "track")):
        if orders:
            summary = _fmt_orders(orders)
            return f"Here are your recent orders:\n{summary}"
        return "You don't have any orders yet. Pick a garment to place your first one."

    if "blouse" in lower or "lehenga" in lower:
        if bust is not None:
            return (
                f"For a fitted blouse at bust {bust:.1f} cm, add 5–8 cm ease "
                f"({round(bust + 5)}–{round(bust + 8)} cm cut). "
                "Share a reference photo for neckline and sleeve length."
            )
    if "waist" in lower and waist is not None:
        return f"Waist {waist:.1f} cm — specify garment (skirt, trousers, lehenga) and desired fit."
    if "hip" in lower and hip is not None:
        return f"Hip {hip:.1f} cm — use for bottoms; add 4–6 cm ease for lehenga or palazzo."
    return (
        "Happy to help! Ask me to suggest a garment, advise on fit or fabric, or "
        "tell you about your orders."
    )


def _invoke_bedrock_sync(system: str, user_text: str, max_tokens: int) -> str | None:
    """Blocking Bedrock converse call — run via asyncio.to_thread."""
    resp = _get_bedrock().converse(
        modelId=BEDROCK_MODEL_ID,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user_text}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.6},
    )
    blocks = (resp.get("output", {}).get("message", {}) or {}).get("content") or []
    texts = [b["text"] for b in blocks if b.get("text")]
    return "\n".join(texts).strip() if texts else None


async def _call_bedrock(*, system: str, user_text: str, max_tokens: int) -> str | None:
    try:
        return await asyncio.to_thread(
            _invoke_bedrock_sync, system, user_text, max_tokens
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("assistant Bedrock call failed: %s", exc)
        return None


async def _call_llm(*, system: str, user_text: str, max_tokens: int = 512) -> str | None:
    """Dispatch to the configured LLM backend; None -> use the rule fallback."""
    if BEDROCK_MODEL_ID:
        return await _call_bedrock(
            system=system, user_text=user_text, max_tokens=max_tokens
        )
    if ANTHROPIC_API_KEY:
        return await _call_anthropic(
            system=system, user_text=user_text, max_tokens=max_tokens
        )
    return None


async def _call_anthropic(
    *,
    system: str,
    user_text: str,
    max_tokens: int = 512,
) -> str | None:
    if not ANTHROPIC_API_KEY:
        return None
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_text}],
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            res = await client.post(ANTHROPIC_URL, headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()
            blocks = data.get("content") or []
            texts = [b["text"] for b in blocks if b.get("type") == "text" and b.get("text")]
            return "\n".join(texts).strip() if texts else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("assistant LLM call failed: %s", exc)
        return None


async def suggest_garments(
    measurements: dict[str, Any],
    *,
    calibrated: bool = False,
    context: str | None = None,
    gender: str = "female",
    garment: str | None = None,
    orders: list[dict[str, Any]] | None = None,
    personas: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Proactive garment suggestions after scan or calibration."""
    meas_line = _fmt_measurements(measurements)
    prompt = (
        f"Wearer: {gender}.\n"
        f"Body measurements: {meas_line}.\n"
        f"Calibrated with tape: {'yes' if calibrated else 'no'}.\n"
    )
    if garment:
        prompt += f"Designing a {garment}.\n"
    if context:
        prompt += f"Context: {context}\n"
    ctx = _context_block(orders, personas)
    if ctx:
        prompt += ctx + "\n"
    prompt += "Suggest gender-appropriate garment options with ease in cm."

    text = await _call_llm(
        system=_suggest_system(gender, garment), user_text=prompt
    )
    if text:
        return {"suggestions": text, "source": "llm", "garments": _extract_garments(text)}

    return _rule_suggest(measurements, calibrated=calibrated, gender=gender)


async def chat_reply(
    measurements: dict[str, Any],
    user_message: str,
    history: list[dict[str, str]] | None = None,
    *,
    gender: str = "female",
    garment: str | None = None,
    orders: list[dict[str, Any]] | None = None,
    personas: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Answer a follow-up sizing question, with awareness of the user's orders."""
    hist_lines = []
    for msg in (history or [])[-6:]:
        role = msg.get("role", "user")
        text = msg.get("text", "")
        if text:
            hist_lines.append(f"{role}: {text}")

    prompt = f"Wearer: {gender}. Measurements: {_fmt_measurements(measurements)}\n"
    ctx = _context_block(orders, personas)
    if ctx:
        prompt += ctx + "\n"
    if hist_lines:
        prompt += "Conversation:\n" + "\n".join(hist_lines) + "\n"
    prompt += f"User: {user_message}\nAssistant:"

    text = await _call_llm(system=_chat_system(gender, garment), user_text=prompt)
    if text:
        return {"reply": text, "source": "llm"}

    return {
        "reply": _rule_chat(measurements, user_message, orders),
        "source": "rules",
    }


def _extract_garments(text: str) -> list[str]:
    lower = text.lower()
    found = []
    for g in (
        "blouse", "saree", "kurta", "lehenga", "salwar", "palazzo", "dress",
        "shirt", "sherwani", "nehru jacket", "trousers",
    ):
        if g in lower:
            found.append(g)
    return found[:5]
