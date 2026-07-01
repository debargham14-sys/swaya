"""Collaboration sessions + chat messages in DynamoDB.

A *session* links a user and a designer around one shared, editable avatar
design. The shared source of truth is the ``design`` JSON blob plus a
monotonically increasing ``version`` — clients poll ``sync`` and re-apply the
design whenever ``version`` advances (there is no realtime/WebSocket layer).

Two single-key tables:
  - ``collab_sessions`` keyed by ``session_id``
  - ``collab_messages``  keyed by ``message_id`` (filtered by ``session_id``)

Scoping: every read/mutation passes the caller's uid; only the session's
``user_id`` or ``designer_id`` may touch it. List/scan + in-Python sort is the
low-volume beta convention (add a GSI on session_id/created_at before scaling).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from boto3.dynamodb.conditions import Attr

from api.db.dynamo import from_item, get_table, to_item

# Roles within a session.
ROLE_USER = "user"
ROLE_DESIGNER = "designer"

_SESSION_CLIENT_FIELDS = (
    "user_id",
    "designer_id",
    "user_name",
    "designer_name",
    "status",
    "design",
    "version",
    "updated_by",
    "last_message",
    "user_unread",
    "designer_unread",
    "created_at",
    "updated_at",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session_to_client(doc: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"id": doc.get("session_id")}
    for key in _SESSION_CLIENT_FIELDS:
        out[key] = doc.get(key)
    out["design"] = doc.get("design") or {}
    out["version"] = int(doc.get("version") or 1)
    out["user_unread"] = int(doc.get("user_unread") or 0)
    out["designer_unread"] = int(doc.get("designer_unread") or 0)
    return out


def _message_to_client(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc.get("message_id"),
        "session_id": doc.get("session_id"),
        "sender_role": doc.get("sender_role"),
        "sender_id": doc.get("sender_id"),
        "text": doc.get("text"),
        "created_at": doc.get("created_at"),
    }


class CollabRepository:
    TABLE = "collab_sessions"

    def __init__(self) -> None:
        self._table = get_table(self.TABLE)

    @staticmethod
    def new_id() -> str:
        return f"CS-{uuid4().hex[:12]}"

    # --- reads --------------------------------------------------------------

    def _raw(self, session_id: str) -> dict[str, Any] | None:
        item = self._table.get_item(Key={"session_id": session_id}).get("Item")
        return from_item(item) if item else None

    def role_for(self, doc: dict[str, Any], uid: str) -> str | None:
        if uid and doc.get("user_id") == uid:
            return ROLE_USER
        if uid and doc.get("designer_id") == uid:
            return ROLE_DESIGNER
        return None

    def get(self, session_id: str, uid: str) -> dict[str, Any] | None:
        """Return the session as a client dict, or None if missing/not a member."""
        doc = self._raw(session_id)
        if not doc or self.role_for(doc, uid) is None:
            return None
        return _session_to_client(doc)

    def list_for(self, uid: str, *, role: str, limit: int = 200) -> list[dict[str, Any]]:
        attr = "user_id" if role == ROLE_USER else "designer_id"
        docs: list[dict[str, Any]] = []
        kwargs: dict[str, Any] = {"FilterExpression": Attr(attr).eq(uid)}
        while True:
            resp = self._table.scan(**kwargs)
            docs.extend(from_item(i) for i in resp.get("Items", []))
            start = resp.get("LastEvaluatedKey")
            if not start:
                break
            kwargs["ExclusiveStartKey"] = start
        docs.sort(key=lambda d: d.get("updated_at") or "", reverse=True)
        return [_session_to_client(d) for d in docs[:limit]]

    # --- writes -------------------------------------------------------------

    def create_session(
        self,
        *,
        user_id: str,
        designer_id: str,
        user_name: str | None,
        designer_name: str | None,
        design: dict[str, Any],
    ) -> dict[str, Any]:
        now = _now()
        doc = {
            "session_id": self.new_id(),
            "user_id": user_id,
            "designer_id": designer_id,
            "user_name": user_name,
            "designer_name": designer_name,
            "status": "pending",
            "design": design or {},
            "version": 1,
            "updated_by": ROLE_USER,
            "last_message": None,
            "user_unread": 0,
            "designer_unread": 0,
            "created_at": now,
            "updated_at": now,
        }
        self._table.put_item(Item=to_item(doc))
        return _session_to_client(doc)

    def accept(self, session_id: str, uid: str) -> dict[str, Any] | None:
        doc = self._raw(session_id)
        if not doc or doc.get("designer_id") != uid:
            return None
        doc["status"] = "active"
        doc["updated_at"] = _now()
        self._table.put_item(Item=to_item(doc))
        return _session_to_client(doc)

    def end(self, session_id: str, uid: str) -> dict[str, Any] | None:
        doc = self._raw(session_id)
        if not doc or self.role_for(doc, uid) is None:
            return None
        doc["status"] = "ended"
        doc["updated_at"] = _now()
        self._table.put_item(Item=to_item(doc))
        return _session_to_client(doc)

    def update_design(
        self, session_id: str, uid: str, design: dict[str, Any]
    ) -> dict[str, Any] | None:
        doc = self._raw(session_id)
        if not doc:
            return None
        role = self.role_for(doc, uid)
        if role is None:
            return None
        doc["design"] = design or {}
        doc["version"] = int(doc.get("version") or 1) + 1
        doc["updated_by"] = role
        doc["updated_at"] = _now()
        self._table.put_item(Item=to_item(doc))
        return _session_to_client(doc)

    def clear_unread(self, session_id: str, role: str) -> None:
        doc = self._raw(session_id)
        if not doc:
            return
        key = "user_unread" if role == ROLE_USER else "designer_unread"
        if doc.get(key):
            doc[key] = 0
            self._table.put_item(Item=to_item(doc))

    def note_message(self, session_id: str, sender_role: str, text: str) -> None:
        """Bump the *other* party's unread badge + denormalize last message."""
        doc = self._raw(session_id)
        if not doc:
            return
        other = "designer_unread" if sender_role == ROLE_USER else "user_unread"
        doc[other] = int(doc.get(other) or 0) + 1
        doc["last_message"] = text[:120]
        doc["updated_at"] = _now()
        self._table.put_item(Item=to_item(doc))


class CollabMessageRepository:
    TABLE = "collab_messages"

    def __init__(self) -> None:
        self._table = get_table(self.TABLE)

    @staticmethod
    def new_id() -> str:
        return f"CM-{uuid4().hex}"

    def add(
        self, *, session_id: str, sender_role: str, sender_id: str, text: str
    ) -> dict[str, Any]:
        doc = {
            "message_id": self.new_id(),
            "session_id": session_id,
            "sender_role": sender_role,
            "sender_id": sender_id,
            "text": text,
            "created_at": _now(),
        }
        self._table.put_item(Item=to_item(doc))
        return _message_to_client(doc)

    def list_since(
        self, session_id: str, *, since: str | None = None, limit: int = 500
    ) -> list[dict[str, Any]]:
        flt = Attr("session_id").eq(session_id)
        if since:
            flt = flt & Attr("created_at").gt(since)
        docs: list[dict[str, Any]] = []
        kwargs: dict[str, Any] = {"FilterExpression": flt}
        while True:
            resp = self._table.scan(**kwargs)
            docs.extend(from_item(i) for i in resp.get("Items", []))
            start = resp.get("LastEvaluatedKey")
            if not start:
                break
            kwargs["ExclusiveStartKey"] = start
        docs.sort(key=lambda d: d.get("created_at") or "")
        return [_message_to_client(d) for d in docs[:limit]]
