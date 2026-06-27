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
        }
        # Carry forward previously-stored values, then apply provided non-null ones.
        for key in _FIELDS:
            value = fields.get(key)
            doc[key] = value if value not in (None, "") else existing.get(key)
        self._table.put_item(Item=to_item(doc))
        return doc
