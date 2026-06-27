"""Persona records (a named profile + its blouse measurements) in DynamoDB.

Keyed by ``persona_id`` (the id the app already generates) and scoped to the
owning Firebase uid via a stored ``user_id`` attribute + ownership checks — the
same convention as ``scans``. Measurements live embedded in the item (a small
{field -> cm} map), so there is no separate measurements table.

List uses a filtered Scan + in-Python sort (low-volume beta convention; add a
GSI on user_id/updated_at before scaling — see scans.py).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr

from api.db.dynamo import from_item, get_table, to_item


def _to_client(doc: dict[str, Any]) -> dict[str, Any]:
    """Storage item -> the JSON shape the app's Persona.fromJson expects."""
    return {
        "id": doc.get("persona_id"),
        "name": doc.get("name"),
        "label": doc.get("label"),
        "measurements": doc.get("measurements", {}),
        "updated_at": doc.get("updated_at"),
    }


class PersonaRepository:
    TABLE = "personas"

    def __init__(self) -> None:
        self._table = get_table(self.TABLE)

    def get(self, user_id: str, persona_id: str) -> dict[str, Any] | None:
        item = self._table.get_item(Key={"persona_id": persona_id}).get("Item")
        if not item:
            return None
        doc = from_item(item)
        if user_id and doc.get("user_id") not in (None, user_id):
            return None  # not the caller's persona
        return doc

    def list(self, user_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        kwargs: dict[str, Any] = {"FilterExpression": Attr("user_id").eq(user_id)}
        while True:
            resp = self._table.scan(**kwargs)
            docs.extend(from_item(i) for i in resp.get("Items", []))
            start = resp.get("LastEvaluatedKey")
            if not start:
                break
            kwargs["ExclusiveStartKey"] = start
        docs.sort(key=lambda d: d.get("updated_at") or "", reverse=True)
        return [_to_client(d) for d in docs[:limit]]

    def upsert(
        self,
        user_id: str,
        persona_id: str,
        *,
        name: str,
        label: str | None,
        measurements: dict[str, float],
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get(user_id, persona_id)
        doc = {
            "persona_id": persona_id,
            "user_id": user_id,
            "name": name,
            "label": label,
            "measurements": measurements or {},
            "created_at": (existing or {}).get("created_at", now),
            "updated_at": now,
        }
        self._table.put_item(Item=to_item(doc))
        return _to_client(doc)

    def delete(self, user_id: str, persona_id: str) -> bool:
        # Ownership-checked: only delete if it belongs to the caller.
        if self.get(user_id, persona_id) is None:
            return False
        self._table.delete_item(Key={"persona_id": persona_id})
        return True
