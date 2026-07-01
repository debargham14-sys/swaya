"""User profile records in DynamoDB, keyed directly by the Firebase uid.

Stores the identity fields the app collects (email, name, phone) so we have a
durable user record independent of Firebase. Upsert merges — a later call that
omits a field won't wipe a value an earlier call set.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from api.db.dynamo import from_item, get_table, to_item

_FIELDS = ("email", "name", "phone")


class UserRepository:
    TABLE = "users"

    def __init__(self) -> None:
        self._table = get_table(self.TABLE)

    def get(self, uid: str) -> dict[str, Any] | None:
        item = self._table.get_item(Key={"uid": uid}).get("Item")
        return from_item(item) if item else None

    def upsert(self, uid: str, **fields: Any) -> dict[str, Any]:
        """Create or update the user record, merging non-null fields."""
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get(uid) or {}
        doc: dict[str, Any] = {
            "uid": uid,
            "created_at": existing.get("created_at", now),
            "updated_at": now,
            "last_seen": now,
            # 'user' | 'designer' — carried forward; defaults to user.
            "role": existing.get("role", "user"),
            # Push-notification device tokens are independent of profile edits.
            "fcm_tokens": list(existing.get("fcm_tokens") or []),
        }
        # Carry forward previously-stored values, then apply provided non-null ones.
        for key in _FIELDS:
            value = fields.get(key)
            doc[key] = value if value not in (None, "") else existing.get(key)
        self._table.put_item(Item=to_item(doc))
        return doc

    def add_fcm_token(self, uid: str, token: str) -> list[str]:
        """Register a device's FCM token for push notifications (deduped)."""
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get(uid) or {}
        tokens = list(existing.get("fcm_tokens") or [])
        if token and token not in tokens:
            tokens.append(token)
        # Keep the list bounded — a user has only so many devices.
        tokens = tokens[-10:]
        doc = {
            **existing,
            "uid": uid,
            "fcm_tokens": tokens,
            "created_at": existing.get("created_at", now),
            "updated_at": now,
        }
        doc.setdefault("role", "user")
        self._table.put_item(Item=to_item(doc))
        return tokens

    def get_fcm_tokens(self, uid: str) -> list[str]:
        return list((self.get(uid) or {}).get("fcm_tokens") or [])

    def remove_fcm_tokens(self, uid: str, tokens: list[str]) -> None:
        """Drop tokens FCM reported as unregistered/invalid."""
        if not tokens:
            return
        existing = self.get(uid)
        if not existing:
            return
        existing["fcm_tokens"] = [
            t for t in (existing.get("fcm_tokens") or []) if t not in tokens
        ]
        existing["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._table.put_item(Item=to_item(existing))

    def set_role(self, uid: str, role: str) -> dict[str, Any]:
        """Set the user's role ('user' | 'designer'), creating the record if needed."""
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get(uid) or {}
        doc = {
            **existing,
            "uid": uid,
            "role": role,
            "created_at": existing.get("created_at", now),
            "updated_at": now,
        }
        self._table.put_item(Item=to_item(doc))
        return doc
