"""Designer directory API tests (in-process DynamoDB via moto).

Auth is disabled in tests, so we override ``current_uid`` with a header-driven
identity (``X-Test-Uid``) to exercise per-user scoping and designer gating.
"""

from __future__ import annotations

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

pytest.importorskip("moto")


def _uid_override(request: Request) -> str:
    return request.headers.get("X-Test-Uid", "anon")


@pytest.fixture
def client(aws_backend):
    from api.auth import current_uid
    from api.main import app

    app.dependency_overrides[current_uid] = _uid_override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _h(uid: str) -> dict:
    return {"X-Test-Uid": uid}


def test_register_makes_a_designer_and_appears_in_directory(client):
    # Not a designer yet.
    me = client.get("/v1/designers/me", headers=_h("d1"))
    assert me.status_code == 200
    assert me.json()["designer"] is None

    res = client.post(
        "/v1/designers/me",
        headers=_h("d1"),
        json={"name": "Aanya", "specialties": ["Blouse"], "available": True},
    )
    assert res.status_code == 200, res.text
    assert res.json()["id"] == "d1"
    assert res.json()["name"] == "Aanya"

    me = client.get("/v1/designers/me", headers=_h("d1")).json()["designer"]
    assert me["id"] == "d1"

    listed = client.get("/v1/designers", headers=_h("someone")).json()["designers"]
    assert any(d["id"] == "d1" for d in listed)


def test_available_filter(client):
    client.post("/v1/designers/me", headers=_h("on"), json={"name": "On", "available": True})
    client.post("/v1/designers/me", headers=_h("off"), json={"name": "Off", "available": False})

    avail = client.get("/v1/designers?available=1", headers=_h("x")).json()["designers"]
    ids = {d["id"] for d in avail}
    assert "on" in ids and "off" not in ids


def test_seed_and_get_one(client):
    seeded = client.post("/v1/designers/seed", headers=_h("admin")).json()["designers"]
    assert len(seeded) >= 3
    one = seeded[0]["id"]
    got = client.get(f"/v1/designers/{one}", headers=_h("x"))
    assert got.status_code == 200
    assert got.json()["id"] == one

    missing = client.get("/v1/designers/nope", headers=_h("x"))
    assert missing.status_code == 404


def test_rating_aggregates(client):
    client.post("/v1/designers/me", headers=_h("d2"), json={"name": "Rated"})
    r1 = client.post("/v1/designers/d2/rating", headers=_h("u1"), json={"stars": 5})
    r2 = client.post("/v1/designers/d2/rating", headers=_h("u2"), json={"stars": 3})
    assert r1.status_code == 200 and r2.status_code == 200
    final = r2.json()
    assert final["rating_count"] == 2
    assert final["rating_avg"] == 4.0  # (5 + 3) / 2

    bad = client.post("/v1/designers/d2/rating", headers=_h("u3"), json={"stars": 9})
    assert bad.status_code == 422  # out of 1..5 range
