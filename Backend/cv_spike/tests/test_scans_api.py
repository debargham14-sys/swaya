"""Scan API tests (run against in-process DynamoDB + S3 via moto)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("moto")

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "tests" / "fixtures" / "profiles"


@pytest.fixture
def client(aws_backend):
    from api.main import app

    return TestClient(app)


def _files():
    return {
        "front": ("front.jpg", (REFS / "front" / "dummy_female_01.jpg").read_bytes(), "image/jpeg"),
        "back": ("back.jpg", (REFS / "back" / "dummy_female_01.jpg").read_bytes(), "image/jpeg"),
        "side": ("side.jpg", (REFS / "side" / "dummy_female_01.jpg").read_bytes(), "image/jpeg"),
    }


@pytest.mark.slow
def test_create_scan_and_download_bundle(client):
    res = client.post(
        "/v1/scans",
        files=_files(),
        data={"mode": "height", "height_cm": "165", "weight_kg": "60", "prefer": "photo"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    scan_id = body["scan_id"]
    assert body["download_url"] == f"/v1/scans/{scan_id}/bundle"
    assert "measurements" in body
    assert body["measurements"]["girths_cm"]

    dl = client.get(f"/v1/scans/{scan_id}/bundle")
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "application/zip"
    assert len(dl.content) > 500

    listed = client.get("/v1/scans?limit=5")
    assert listed.status_code == 200
    assert any(s["scan_id"] == scan_id for s in listed.json()["scans"])

    photo = client.get(f"/v1/scans/{scan_id}/photos/front")
    assert photo.status_code == 200
    assert photo.headers["content-type"].startswith("image/")
    assert len(photo.content) > 1000
