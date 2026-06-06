"""Fit assistant API tests (no LLM key required — uses rule fallback)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


def test_assistant_status(client):
    res = client.get("/v1/assistant/status")
    assert res.status_code == 200
    body = res.json()
    assert "llm_available" in body
    assert body["fallback"] == "rules"


def test_suggest_without_llm(client):
    res = client.post(
        "/v1/assistant/suggest",
        json={
            "measurements": {
                "girths_cm": {"bust": 88.0, "waist": 72.0, "hip": 96.0},
                "height_cm": 165.0,
            },
            "calibrated": True,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"] == "rules"
    assert "suggestions" in body
    assert "blouse" in body["suggestions"].lower()


def test_chat_without_llm(client):
    res = client.post(
        "/v1/assistant/chat",
        json={
            "measurements": {"girths_cm": {"waist": 72.0}},
            "message": "What about my waist?",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"] == "rules"
    assert "72" in body["reply"]
