"""QC endpoint smoke tests."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from qc_synth import make_qc_jpeg_bytes

SPEC = {
    "order_id": "SW-TEST-0001",
    "tier": "bespoke",
    "variant": "sleeveless",
    "target_dims_mm": {"bust": 860, "total_length": 600, "shoulder_width": 380},
    "features": [],
}


@pytest.fixture(scope="module")
def client():
    from api.main import app

    return TestClient(app)


def test_qc_requires_spec_or_order_id(client):
    files = {"front": ("front.jpg", make_qc_jpeg_bytes(), "image/jpeg")}
    res = client.post("/v1/qc", files=files)
    assert res.status_code == 422


def test_qc_inline_spec_returns_full_report(client):
    files = {"front": ("front.jpg", make_qc_jpeg_bytes(), "image/jpeg")}
    res = client.post("/v1/qc", files=files, data={"spec": json.dumps(SPEC)})
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["order_id"] == "SW-TEST-0001"
    assert body["overall_status"] in {"pass", "fail", "needs_review"}
    assert body["calibration"]["corners_found"] == 4
    assert not body["calibration"]["needs_retake"]
    assert len(body["checks"]) == 47
    # dimensional comparisons present for the specified dimensions
    names = {c["name"] for c in body["comparisons"]}
    assert {"bust", "total_length", "shoulder_width"} <= names
    assert "category_summary" in body


def test_qc_unknown_order_id_404(client):
    files = {"front": ("front.jpg", make_qc_jpeg_bytes(), "image/jpeg")}
    res = client.post("/v1/qc", files=files, data={"order_id": "does-not-exist"})
    assert res.status_code == 404
