"""Collaboration sessions — a user and a designer co-editing one avatar design.

Near-real-time via polling: clients hit ``GET /sessions/{id}/sync`` on an
interval and re-apply the shared ``design`` whenever ``version`` advances. There
is no WebSocket layer (see api/db/collab.py). Every endpoint is membership-
scoped — only the session's user or designer may read/mutate it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import current_uid
from api.db.collab import (
    ROLE_DESIGNER,
    ROLE_USER,
    CollabMessageRepository,
    CollabRepository,
)
from api.db.designers import DesignerRepository
from api.db.dynamo import dynamo_available, dynamo_last_error
from api.db.users import UserRepository
from api.services.push import send_to_uid

router = APIRouter(prefix="/v1/collab", tags=["collab"])


def _require_db() -> None:
    if not dynamo_available():
        raise HTTPException(
            status_code=503,
            detail=f"DynamoDB unavailable: {dynamo_last_error() or 'not configured'}",
        )


class CreateSessionBody(BaseModel):
    designer_id: str
    # Free-form avatar design blob (gender, color_index, sleeves, watch, pants, …).
    design: dict = Field(default_factory=dict)


class DesignBody(BaseModel):
    design: dict = Field(default_factory=dict)


class MessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


def _member_or_404(session_id: str, uid: str) -> dict:
    doc = CollabRepository().get(session_id, uid)
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    return doc


def _role(session: dict, uid: str) -> str:
    return ROLE_USER if session.get("user_id") == uid else ROLE_DESIGNER


@router.post("/sessions")
def create_session(body: CreateSessionBody, uid: str = Depends(current_uid)) -> dict:
    """User starts a collaboration with a chosen designer (status: pending)."""
    _require_db()
    designer = DesignerRepository().get_client(body.designer_id)
    if not designer:
        raise HTTPException(status_code=404, detail="Designer not found.")
    user = UserRepository().get(uid) or {}
    session = CollabRepository().create_session(
        user_id=uid,
        designer_id=body.designer_id,
        user_name=user.get("name"),
        designer_name=designer.get("name"),
        design=body.design,
    )
    # Notify the designer of the incoming request (best-effort push).
    client = user.get("name") or "A client"
    send_to_uid(
        body.designer_id,
        title="New collaboration request",
        body=f"{client} wants to design a blouse with you.",
        data={"type": "collab_invite", "session_id": session["id"]},
    )
    return session


@router.get("/sessions")
def list_sessions(
    role: str = Query("user"), uid: str = Depends(current_uid)
) -> dict:
    """The caller's sessions. ``?role=user`` (default) or ``?role=designer``."""
    _require_db()
    role = ROLE_DESIGNER if role == ROLE_DESIGNER else ROLE_USER
    return {"sessions": CollabRepository().list_for(uid, role=role)}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, uid: str = Depends(current_uid)) -> dict:
    _require_db()
    return _member_or_404(session_id, uid)


@router.get("/sessions/{session_id}/sync")
def sync_session(
    session_id: str,
    since: str | None = Query(None),
    uid: str = Depends(current_uid),
) -> dict:
    """The single polling endpoint: current session + messages since ``since``.

    Also clears the caller's unread badge (they're looking at it).
    """
    _require_db()
    session = _member_or_404(session_id, uid)
    role = _role(session, uid)
    repo = CollabRepository()
    repo.clear_unread(session_id, role)
    messages = CollabMessageRepository().list_since(session_id, since=since)
    session["user_unread" if role == ROLE_USER else "designer_unread"] = 0
    return {
        "session": session,
        "design": session.get("design") or {},
        "version": session.get("version") or 1,
        "status": session.get("status"),
        "messages": messages,
    }


@router.post("/sessions/{session_id}/accept")
def accept_session(session_id: str, uid: str = Depends(current_uid)) -> dict:
    """Designer accepts a pending request (status: active)."""
    _require_db()
    doc = CollabRepository().accept(session_id, uid)
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    # Tell the client their request was accepted.
    send_to_uid(
        doc["user_id"],
        title="Request accepted",
        body=f"{doc.get('designer_name') or 'Your designer'} accepted — start designing!",
        data={"type": "collab_accepted", "session_id": session_id},
    )
    return doc


@router.patch("/sessions/{session_id}/design")
def update_design(
    session_id: str, body: DesignBody, uid: str = Depends(current_uid)
) -> dict:
    """Either party edits the shared design; bumps ``version``."""
    _require_db()
    doc = CollabRepository().update_design(session_id, uid, body.design)
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    return doc


@router.post("/sessions/{session_id}/messages")
def post_message(
    session_id: str, body: MessageBody, uid: str = Depends(current_uid)
) -> dict:
    _require_db()
    session = _member_or_404(session_id, uid)
    role = _role(session, uid)
    msg = CollabMessageRepository().add(
        session_id=session_id, sender_role=role, sender_id=uid, text=body.text
    )
    CollabRepository().note_message(session_id, role, body.text)
    # Notify the *other* party of the new message.
    recipient = session["designer_id"] if role == ROLE_USER else session["user_id"]
    sender_name = (
        session.get("user_name") if role == ROLE_USER else session.get("designer_name")
    ) or "New message"
    send_to_uid(
        recipient,
        title=sender_name,
        body=body.text,
        data={"type": "collab_message", "session_id": session_id},
    )
    return msg


@router.post("/sessions/{session_id}/end")
def end_session(session_id: str, uid: str = Depends(current_uid)) -> dict:
    _require_db()
    doc = CollabRepository().end(session_id, uid)
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found.")
    return doc
