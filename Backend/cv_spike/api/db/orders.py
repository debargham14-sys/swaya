"""Order records (blouse orders, alterations, cancellations) in DynamoDB.

Keyed by ``order_id`` and scoped to the owning Firebase uid via a stored
``user_id`` attribute + ownership checks — same convention as scans/personas.
Each order carries a ``category`` (active | delivered | alterations | cancelled)
that drives which tab it shows under in the app, plus a ``status`` badge.

List is a filtered Scan + in-Python sort (low-volume beta; add a GSI on
user_id/updated_at before scaling).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from boto3.dynamodb.conditions import Attr

from api.db.dynamo import from_item, get_table, to_item

_CLIENT_FIELDS = (
    "garment",
    "category",
    "status",
    "placed_on",
    "estimated_date",
    "location",
    "subtotal",
    "shipping",
    "total",
    "tracking",
    "delivery_person",
    "delivery_phone",
    "note_title",
    "note_body",
    "updated_at",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_client(doc: dict[str, Any]) -> dict[str, Any]:
    """Storage item -> the JSON shape the app's BlouseOrder.fromJson expects."""
    out: dict[str, Any] = {"id": doc.get("order_id")}
    for key in _CLIENT_FIELDS:
        out[key] = doc.get(key)
    return out


class OrderRepository:
    TABLE = "orders"

    def __init__(self) -> None:
        self._table = get_table(self.TABLE)

    @staticmethod
    def new_id(prefix: str = "SW") -> str:
        return f"{prefix}-{uuid4().hex[:8].upper()}"

    def get(self, user_id: str, order_id: str) -> dict[str, Any] | None:
        item = self._table.get_item(Key={"order_id": order_id}).get("Item")
        if not item:
            return None
        doc = from_item(item)
        if user_id and doc.get("user_id") not in (None, user_id):
            return None
        return doc

    def list(
        self, user_id: str, *, category: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        flt = Attr("user_id").eq(user_id)
        if category:
            flt = flt & Attr("category").eq(category)
        docs: list[dict[str, Any]] = []
        kwargs: dict[str, Any] = {"FilterExpression": flt}
        while True:
            resp = self._table.scan(**kwargs)
            docs.extend(from_item(i) for i in resp.get("Items", []))
            start = resp.get("LastEvaluatedKey")
            if not start:
                break
            kwargs["ExclusiveStartKey"] = start
        docs.sort(key=lambda d: d.get("updated_at") or "", reverse=True)
        return [_to_client(d) for d in docs[:limit]]

    def _put(self, doc: dict[str, Any]) -> dict[str, Any]:
        self._table.put_item(Item=to_item(doc))
        return _to_client(doc)

    def create(self, user_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        order_id = fields.get("id") or self.new_id()
        now = _now()
        doc = {
            "order_id": order_id,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
            **{k: fields.get(k) for k in _CLIENT_FIELDS if k != "updated_at"},
        }
        # _CLIENT_FIELDS pulls these in as None when omitted, so setdefault
        # won't help — coalesce explicitly.
        doc["garment"] = doc.get("garment") or "Blouse"
        doc["category"] = doc.get("category") or "active"
        doc["status"] = doc.get("status") or "processing"
        return self._put(doc)

    def upsert(
        self, user_id: str, order_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        existing = self.get(user_id, order_id)
        now = _now()
        doc = {
            "order_id": order_id,
            "user_id": user_id,
            "created_at": (existing or {}).get("created_at", now),
            "updated_at": now,
            **{k: fields.get(k) for k in _CLIENT_FIELDS if k != "updated_at"},
        }
        return self._put(doc)

    def cancel(
        self, user_id: str, order_id: str, reason: str
    ) -> dict[str, Any] | None:
        doc = self.get(user_id, order_id)
        if doc is None:
            return None
        doc.update(
            category="cancelled",
            status="cancelled",
            note_title="Cancellation reason",
            note_body=reason,
            updated_at=_now(),
        )
        return self._put(doc)

    def request_alteration(
        self, user_id: str, order_id: str, description: str
    ) -> dict[str, Any] | None:
        """Create a new Alterations entry derived from a delivered order."""
        src = self.get(user_id, order_id)
        if src is None:
            return None
        now = _now()
        alt = {
            "order_id": self.new_id("ALT"),
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
            "garment": src.get("garment", "Blouse"),
            "category": "alterations",
            "status": "processing",
            "placed_on": src.get("placed_on"),
            "estimated_date": src.get("estimated_date"),
            "location": src.get("location"),
            "subtotal": src.get("subtotal", 0),
            "shipping": src.get("shipping", 0),
            "total": src.get("total", 0),
            "tracking": _TRACK_PROCESSING,
            "note_title": "Alteration request",
            "note_body": description,
            "source_order_id": order_id,
        }
        return self._put(alt)

    def delete(self, user_id: str, order_id: str) -> bool:
        if self.get(user_id, order_id) is None:
            return False
        self._table.delete_item(Key={"order_id": order_id})
        return True

    def seed_samples(self, user_id: str) -> list[dict[str, Any]]:
        """Insert demo orders for a user that has none (idempotent-ish)."""
        if self.list(user_id, limit=1):
            return self.list(user_id)
        now = _now()
        for s in _SAMPLE_ORDERS:
            self._table.put_item(
                Item=to_item(
                    {
                        "order_id": s["id"],
                        "user_id": user_id,
                        "created_at": now,
                        "updated_at": now,
                        **{k: s.get(k) for k in _CLIENT_FIELDS if k != "updated_at"},
                    }
                )
            )
        return self.list(user_id)


# --- tracking templates + sample seed data ---------------------------------

_TRACK_PROCESSING = [
    {"label": "Ordered", "done": True},
    {"label": "Processing", "done": True},
    {"label": "Shipped", "done": False},
    {"label": "Delivered", "done": False},
]
_TRACK_SHIPPED = [
    {"label": "Ordered", "done": True},
    {"label": "Processing", "done": True},
    {"label": "Shipped", "done": True},
    {"label": "Delivered", "done": False},
]
_TRACK_DELIVERED = [
    {"label": "Ordered", "done": True},
    {"label": "Processing", "done": True},
    {"label": "Shipped", "done": True},
    {"label": "Delivered", "done": True},
]

_LOC = "Bangalore, Karnataka, 560034"

_SAMPLE_ORDERS = [
    {
        "id": "SW-2024-001", "category": "active", "status": "processing",
        "placed_on": "1 Jun 2026", "estimated_date": "15 Jun 2026", "location": _LOC,
        "subtotal": 2160, "shipping": 0, "total": 2160, "tracking": _TRACK_PROCESSING,
    },
    {
        "id": "SW-2024-002", "category": "active", "status": "shipped",
        "placed_on": "4 Jun 2026", "estimated_date": "12 Jun 2026", "location": _LOC,
        "subtotal": 2160, "shipping": 0, "total": 2160, "tracking": _TRACK_SHIPPED,
        "delivery_person": "C. Ravi Kumar", "delivery_phone": "+91 9876543210",
    },
    {
        "id": "SW-2024-003", "category": "delivered", "status": "delivered",
        "placed_on": "15 Jun 2026", "estimated_date": "15 Jun 2026", "location": _LOC,
        "subtotal": 1980, "shipping": 0, "total": 1980, "tracking": _TRACK_DELIVERED,
        "note_title": "Alteration window",
        "note_body": "Request a free alteration within 7 days of delivery.",
    },
    {
        "id": "SW-2024-005", "category": "alterations", "status": "processing",
        "placed_on": "8 Jun 2026", "estimated_date": "18 Jun 2026", "location": _LOC,
        "subtotal": 2160, "shipping": 0, "total": 2160, "tracking": _TRACK_PROCESSING,
        "note_title": "Size Adjustment",
        "note_body": "Make it looser at the waist by 2 inches.",
    },
    {
        "id": "SW-2024-007", "category": "cancelled", "status": "cancelled",
        "placed_on": "1 Jun 2026", "estimated_date": "15 Jun 2026", "location": _LOC,
        "subtotal": 2160, "shipping": 0, "total": 2160, "tracking": _TRACK_PROCESSING,
        "note_title": "Delivery time", "note_body": "Taking too much time for delivery.",
    },
]
