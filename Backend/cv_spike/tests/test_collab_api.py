"""Collaboration session API tests (in-process DynamoDB via moto).

Exercises the full lifecycle a user + designer go through: create -> designer
sees it -> accept -> shared design edits bump version -> sync picks them up ->
chat round-trips with ``since`` filtering -> membership scoping (strangers 404).
"""

from __future__ import annotations

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

pytest.importorskip("moto")

USER = "user-1"
DESIGNER = "designer-1"
STRANGER = "rando-9"


def _uid_override(request: Request) -> str:
    return request.headers.get("X-Test-Uid", "anon")


@pytest.fixture
def client(aws_backend):
    from api.auth import current_uid
    from api.main import app

    app.dependency_overrides[current_uid] = _uid_override
    try:
        c = TestClient(app)
        # Register the designer so create_session can find them.
        c.post("/v1/designers/me", headers={"X-Test-Uid": DESIGNER}, json={"name": "Dee"})
        yield c
    finally:
        app.dependency_overrides.clear()


def _h(uid: str) -> dict:
    return {"X-Test-Uid": uid}


def _create(client) -> str:
    res = client.post(
        "/v1/collab/sessions",
        headers=_h(USER),
        json={"designer_id": DESIGNER, "design": {"gender": "female", "color_index": 0}},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "pending"
    assert body["version"] == 1
    return body["id"]


def test_create_requires_existing_designer(client):
    res = client.post(
        "/v1/collab/sessions",
        headers=_h(USER),
        json={"designer_id": "ghost", "design": {}},
    )
    assert res.status_code == 404


def test_full_lifecycle(client):
    sid = _create(client)

    # Designer sees the pending request in their inbox.
    inbox = client.get("/v1/collab/sessions?role=designer", headers=_h(DESIGNER)).json()
    assert any(s["id"] == sid for s in inbox["sessions"])

    # User sees it under their own list too.
    mine = client.get("/v1/collab/sessions?role=user", headers=_h(USER)).json()
    assert any(s["id"] == sid for s in mine["sessions"])

    # Designer accepts -> active.
    acc = client.post(f"/v1/collab/sessions/{sid}/accept", headers=_h(DESIGNER))
    assert acc.status_code == 200
    assert acc.json()["status"] == "active"

    # User edits the shared design -> version bumps to 2.
    patched = client.patch(
        f"/v1/collab/sessions/{sid}/design",
        headers=_h(USER),
        json={"design": {"gender": "female", "color_index": 2, "sleeves": True}},
    )
    assert patched.status_code == 200
    assert patched.json()["version"] == 2
    assert patched.json()["updated_by"] == "user"

    # Designer syncs and observes the new version + design.
    synced = client.get(f"/v1/collab/sessions/{sid}/sync", headers=_h(DESIGNER)).json()
    assert synced["version"] == 2
    assert synced["design"]["color_index"] == 2
    assert synced["design"]["sleeves"] is True


def test_messaging_and_since_filter(client):
    sid = _create(client)

    m1 = client.post(
        f"/v1/collab/sessions/{sid}/messages",
        headers=_h(USER),
        json={"text": "Hi, can we widen the sleeves?"},
    )
    assert m1.status_code == 200
    first_ts = m1.json()["created_at"]

    # Designer's sync returns the message and clears their unread badge.
    sync1 = client.get(f"/v1/collab/sessions/{sid}/sync", headers=_h(DESIGNER)).json()
    assert len(sync1["messages"]) == 1
    assert sync1["session"]["designer_unread"] == 0

    # Designer replies.
    client.post(
        f"/v1/collab/sessions/{sid}/messages",
        headers=_h(DESIGNER),
        json={"text": "Sure — done."},
    )

    # since=first_ts returns only the newer (designer) message.
    sync2 = client.get(
        f"/v1/collab/sessions/{sid}/sync",
        headers=_h(USER),
        params={"since": first_ts},
    ).json()
    texts = [m["text"] for m in sync2["messages"]]
    assert texts == ["Sure — done."]


def test_membership_scoping(client):
    sid = _create(client)

    # A stranger cannot read, sync, patch, or message the session.
    assert client.get(f"/v1/collab/sessions/{sid}", headers=_h(STRANGER)).status_code == 404
    assert client.get(f"/v1/collab/sessions/{sid}/sync", headers=_h(STRANGER)).status_code == 404
    assert (
        client.patch(
            f"/v1/collab/sessions/{sid}/design", headers=_h(STRANGER), json={"design": {}}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/v1/collab/sessions/{sid}/messages", headers=_h(STRANGER), json={"text": "hi"}
        ).status_code
        == 404
    )


def test_end_session(client):
    sid = _create(client)
    ended = client.post(f"/v1/collab/sessions/{sid}/end", headers=_h(USER))
    assert ended.status_code == 200
    assert ended.json()["status"] == "ended"
