"""Fit assistant: LLM garment suggestions from body measurements."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

_SUGGEST_SYSTEM = """You are a fit assistant for Indian tailoring and ready-to-wear.
Given body girth measurements in cm, suggest 2–3 specific garment types (blouse, kurta, lehenga, saree blouse, etc.)
with practical cutting/ease notes for a tailor or shopper.
Be concise (under 180 words). Use bullet points. Mention cm values from the scan.
If measurements look incomplete, say what else is needed."""


def llm_available() -> bool:
    return bool(ANTHROPIC_API_KEY)


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


def _rule_suggest(measurements: dict[str, Any], *, calibrated: bool) -> dict[str, Any]:
    g = measurements.get("girths_cm") or {}
    bust = g.get("bust")
    waist = g.get("waist")
    hip = g.get("hip")
    lines: list[str] = []

    if calibrated:
        lines.append("Measurements were recalibrated with your tape values — suggestions below use the updated numbers.")

    if bust is not None:
        ease_lo = round(bust + 5)
        ease_hi = round(bust + 8)
        lines.append(
            f"• Fitted blouse / saree blouse: cut bust {ease_lo}–{ease_hi} cm "
            f"(5–8 cm ease over {bust:.1f} cm)."
        )
        lines.append(
            f"• Structured kurta: bust panel ~{round(bust + 10)} cm for comfortable movement."
        )

    if waist is not None:
        lines.append(
            f"• High-waist lehenga / skirt: waist {waist:.1f} cm — add 2–3 cm ease for sitting."
        )

    if hip is not None:
        lines.append(
            f"• Lehenga bottom / palazzo: hip {hip:.1f} cm — allow 4–6 cm ease at hip line."
        )

    if not lines:
        lines.append(
            "Save at least bust or waist tape measurements to unlock tailored garment suggestions."
        )

    return {
        "suggestions": "\n".join(lines),
        "source": "rules",
        "garments": ["blouse", "kurta", "lehenga"] if bust else [],
    }


def _rule_chat(measurements: dict[str, Any], user_message: str) -> str:
    lower = user_message.lower()
    g = measurements.get("girths_cm") or {}
    bust, waist, hip = g.get("bust"), g.get("waist"), g.get("hip")

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
        f"I have bust {bust or '—'} cm, waist {waist or '—'} cm, hip {hip or '—'} cm. "
        "Ask about a specific garment (blouse, kurta, lehenga) or ease."
    )


async def _call_anthropic(
    *,
    system: str,
    user_text: str,
    max_tokens: int = 512,
) -> str | None:
    if not llm_available():
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
) -> dict[str, Any]:
    """Proactive garment suggestions after scan or calibration."""
    meas_line = _fmt_measurements(measurements)
    prompt = (
        f"Body measurements: {meas_line}.\n"
        f"Calibrated with tape: {'yes' if calibrated else 'no'}.\n"
    )
    if context:
        prompt += f"Context: {context}\n"
    prompt += "Suggest blouse, kurta, and lehenga options with ease in cm."

    text = await _call_anthropic(system=_SUGGEST_SYSTEM, user_text=prompt)
    if text:
        return {"suggestions": text, "source": "llm", "garments": _extract_garments(text)}

    out = _rule_suggest(measurements, calibrated=calibrated)
    return out


async def chat_reply(
    measurements: dict[str, Any],
    user_message: str,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Answer a follow-up sizing question."""
    hist_lines = []
    for msg in (history or [])[-6:]:
        role = msg.get("role", "user")
        text = msg.get("text", "")
        if text:
            hist_lines.append(f"{role}: {text}")

    prompt = f"Measurements: {_fmt_measurements(measurements)}\n"
    if hist_lines:
        prompt += "Conversation:\n" + "\n".join(hist_lines) + "\n"
    prompt += f"User: {user_message}\nAssistant:"

    text = await _call_anthropic(
        system=_SUGGEST_SYSTEM + "\nAnswer the user's question in 2–4 short sentences.",
        user_text=prompt,
    )
    if text:
        return {"reply": text, "source": "llm"}

    return {"reply": _rule_chat(measurements, user_message), "source": "rules"}


def _extract_garments(text: str) -> list[str]:
    lower = text.lower()
    found = []
    for g in ("blouse", "kurta", "lehenga", "saree", "salwar", "palazzo", "dress"):
        if g in lower:
            found.append(g)
    return found[:5]
