"""Designer/tailor profiles in DynamoDB, keyed by the designer's Firebase uid.

A "designer" is a regular Firebase user who has registered a public profile
(name, specialties, rating, …). The presence of a row here is what makes a uid
a designer — see ``api.auth.require_designer``. Profiles are browseable by any
signed-in user (the directory), so unlike scans/personas they are *not* scoped
to a single owner on read; only the owning uid can edit their own profile.

List uses a filtered Scan + in-Python sort (low-volume beta convention; add a
GSI before scaling — see scans.py).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr

from api.db.dynamo import from_item, get_table, to_item

# Fields the app's Designer.fromJson expects (besides the id).
_CLIENT_FIELDS = (
    "name",
    "bio",
    "specialties",
    "location",
    "years_experience",
    "price_range",
    "photo_url",
    "available",
    "rating_avg",
    "rating_count",
    "updated_at",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_client(doc: dict[str, Any]) -> dict[str, Any]:
    """Storage item -> the JSON shape the app's Designer.fromJson expects."""
    out: dict[str, Any] = {"id": doc.get("designer_id")}
    for key in _CLIENT_FIELDS:
        out[key] = doc.get(key)
    out["specialties"] = doc.get("specialties") or []
    out["available"] = bool(doc.get("available", True))
    out["rating_avg"] = doc.get("rating_avg") or 0
    out["rating_count"] = doc.get("rating_count") or 0
    return out


class DesignerRepository:
    TABLE = "designers"

    def __init__(self) -> None:
        self._table = get_table(self.TABLE)

    def get(self, designer_id: str) -> dict[str, Any] | None:
        item = self._table.get_item(Key={"designer_id": designer_id}).get("Item")
        return from_item(item) if item else None

    def get_client(self, designer_id: str) -> dict[str, Any] | None:
        doc = self.get(designer_id)
        return _to_client(doc) if doc else None

    def is_designer(self, designer_id: str) -> bool:
        return self.get(designer_id) is not None

    def list(self, *, available_only: bool = False, limit: int = 200) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        kwargs: dict[str, Any] = {}
        if available_only:
            kwargs["FilterExpression"] = Attr("available").eq(True)
        while True:
            resp = self._table.scan(**kwargs)
            docs.extend(from_item(i) for i in resp.get("Items", []))
            start = resp.get("LastEvaluatedKey")
            if not start:
                break
            kwargs["ExclusiveStartKey"] = start
        docs.sort(key=lambda d: (d.get("rating_avg") or 0, d.get("updated_at") or ""), reverse=True)
        return [_to_client(d) for d in docs[:limit]]

    def upsert(self, designer_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Create or update the caller's own designer profile (merges)."""
        now = _now()
        existing = self.get(designer_id) or {}
        doc: dict[str, Any] = {
            "designer_id": designer_id,
            "created_at": existing.get("created_at", now),
            "updated_at": now,
            # Preserve running rating aggregate across profile edits.
            "rating_avg": existing.get("rating_avg", 0),
            "rating_count": existing.get("rating_count", 0),
        }
        for key in _CLIENT_FIELDS:
            if key in ("updated_at", "rating_avg", "rating_count"):
                continue
            value = fields.get(key)
            doc[key] = value if value not in (None, "") else existing.get(key)
        doc["name"] = doc.get("name") or "Designer"
        doc["specialties"] = doc.get("specialties") or []
        doc["available"] = bool(fields.get("available", existing.get("available", True)))
        self._table.put_item(Item=to_item(doc))
        return _to_client(doc)

    def add_rating(self, designer_id: str, stars: float) -> dict[str, Any] | None:
        """Fold a new star rating into the running average."""
        doc = self.get(designer_id)
        if doc is None:
            return None
        count = int(doc.get("rating_count") or 0)
        avg = float(doc.get("rating_avg") or 0)
        new_count = count + 1
        new_avg = (avg * count + float(stars)) / new_count
        doc["rating_count"] = new_count
        doc["rating_avg"] = round(new_avg, 2)
        doc["updated_at"] = _now()
        self._table.put_item(Item=to_item(doc))
        return _to_client(doc)

    def seed_samples(self) -> list[dict[str, Any]]:
        """Insert a few demo designers so the directory isn't empty (idempotent)."""
        for s in _SAMPLE_DESIGNERS:
            if self.get(s["designer_id"]):
                continue
            now = _now()
            self._table.put_item(
                Item=to_item({**s, "created_at": now, "updated_at": now})
            )
        return self.list()


_SAMPLE_DESIGNERS = [
    {
        "designer_id": "demo-designer-aanya",
        "name": "Aanya Kapoor",
        "bio": "Bridal & festive blouse specialist with a love for hand embroidery.",
        "specialties": ["Blouse", "Lehenga", "Bridal"],
        "location": "Bangalore, Karnataka",
        "years_experience": 9,
        "price_range": "₹₹₹",
        "photo_url": None,
        "available": True,
        "rating_avg": 4.8,
        "rating_count": 64,
    },
    {
        "designer_id": "demo-designer-rohan",
        "name": "Rohan Mehta",
        "bio": "Menswear tailor — sherwanis, Nehru jackets and crisp kurtas.",
        "specialties": ["Sherwani", "Kurta", "Nehru jacket"],
        "location": "Mumbai, Maharashtra",
        "years_experience": 12,
        "price_range": "₹₹",
        "photo_url": None,
        "available": True,
        "rating_avg": 4.6,
        "rating_count": 41,
    },
    {
        "designer_id": "demo-designer-meera",
        "name": "Meera Nair",
        "bio": "Contemporary saree blouses and fusion silhouettes.",
        "specialties": ["Saree blouse", "Dress", "Kurta"],
        "location": "Kochi, Kerala",
        "years_experience": 6,
        "price_range": "₹₹",
        "photo_url": None,
        "available": True,
        "rating_avg": 4.9,
        "rating_count": 88,
    },
]
