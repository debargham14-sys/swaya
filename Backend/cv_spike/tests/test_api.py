"""API smoke tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "tests" / "fixtures" / "profiles"


@pytest.fixture(scope="module")
def client():
    from api.main import app

    return TestClient(app)


def _view_path(view: str) -> Path:
    path = REFS / view / "dummy_female_01.jpg"
    assert path.is_file(), f"missing fixture {path}"
    return path


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "backends" in body


def test_measure_requires_mode_or_inputs(client):
    files = {
        "front": ("front.jpg", _view_path("front").read_bytes(), "image/jpeg"),
        "back": ("back.jpg", _view_path("back").read_bytes(), "image/jpeg"),
        "side": ("side.jpg", _view_path("side").read_bytes(), "image/jpeg"),
    }
    res = client.post("/v1/measure", files=files)
    assert res.status_code == 422


def test_measure_requires_photos(client):
    res = client.post("/v1/measure", data={"mode": "aruco", "ref": "aruco"})
    assert res.status_code == 422


@pytest.mark.slow
def test_measure_aruco_flow(client):
    files = {
        "front": ("front.jpg", _view_path("front").read_bytes(), "image/jpeg"),
        "back": ("back.jpg", _view_path("back").read_bytes(), "image/jpeg"),
        "side": ("side.jpg", _view_path("side").read_bytes(), "image/jpeg"),
    }
    res = client.post(
        "/v1/measure",
        files=files,
        data={"mode": "aruco", "ref": "aruco", "ref_mm": "50"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "aruco"
    assert body["backend"] == "photo:body-slice"


@pytest.mark.slow
def test_measure_height_flow_photo(client):
    files = {
        "front": ("front.jpg", _view_path("front").read_bytes(), "image/jpeg"),
        "back": ("back.jpg", _view_path("back").read_bytes(), "image/jpeg"),
        "side": ("side.jpg", _view_path("side").read_bytes(), "image/jpeg"),
    }
    data = {"mode": "height", "height_cm": "165", "weight_kg": "60", "prefer": "photo"}
    res = client.post("/v1/measure", files=files, data=data)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "height"
    assert body["height_cm"] == 165
    assert body["weight_kg"] == 60
    assert body["girths_cm"]
    assert body["backend"] == "photo:body-slice"


@pytest.mark.slow
def test_measure_height_endpoint(client):
    files = {
        "front": ("front.jpg", _view_path("front").read_bytes(), "image/jpeg"),
        "back": ("back.jpg", _view_path("back").read_bytes(), "image/jpeg"),
        "side": ("side.jpg", _view_path("side").read_bytes(), "image/jpeg"),
    }
    res = client.post(
        "/v1/measure/height",
        files=files,
        data={"height_cm": "165", "weight_kg": "60", "prefer": "photo"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["mode"] == "height"


@pytest.mark.slow
def test_measure_returns_girths(client):
    files = {
        "front": ("front.jpg", _view_path("front").read_bytes(), "image/jpeg"),
        "back": ("back.jpg", _view_path("back").read_bytes(), "image/jpeg"),
        "side": ("side.jpg", _view_path("side").read_bytes(), "image/jpeg"),
    }
    data = {"mode": "height", "height_cm": "165", "weight_kg": "60", "prefer": "photo"}
    res = client.post("/v1/measure", files=files, data=data)
    assert res.status_code == 200, res.text
    body = res.json()
    assert "girths_cm" in body
    assert body["girths_cm"]
    for key in ("bust", "waist", "hip"):
        assert key in body["girths_cm"]
    assert body["girths_in"]
    assert body["backend"]
