"""Orders — blouse orders, alterations and cancellations, scoped to the caller."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import current_uid
from api.db.dynamo import dynamo_available, dynamo_last_error
from api.db.orders import OrderRepository

router = APIRouter(prefix="/v1/orders", tags=["orders"])


def _require_db() -> None:
    if not dynamo_available():
        raise HTTPException(
            status_code=503,
            detail=f"DynamoDB unavailable: {dynamo_last_error() or 'not configured'}",
        )


class TrackingStep(BaseModel):
    label: str
    done: bool = False


class OrderBody(BaseModel):
    garment: str = "Blouse"  # the garment type ordered (gender-appropriate label)
    category: str = "active"  # active | delivered | alterations | cancelled
    status: str = "processing"  # processing | shipped | delivered | cancelled
    placed_on: str | None = None
    estimated_date: str | None = None
    location: str | None = None
    subtotal: float = 0
    shipping: float = 0
    total: float = 0
    tracking: list[TrackingStep] = Field(default_factory=list)
    delivery_person: str | None = None
    delivery_phone: str | None = None
    note_title: str | None = None
    note_body: str | None = None


class CancelBody(BaseModel):
    reason: str


class AlterationBody(BaseModel):
    description: str


@router.get("")
def list_orders(
    category: str | None = Query(None), uid: str = Depends(current_uid)
) -> dict:
    """The caller's orders, newest first; optional ?category= filter."""
    _require_db()
    return {"orders": OrderRepository().list(uid, category=category)}


@router.post("")
def create_order(body: OrderBody, uid: str = Depends(current_uid)) -> dict:
    _require_db()
    return OrderRepository().create(uid, body.model_dump())


@router.post("/seed")
def seed_orders(uid: str = Depends(current_uid)) -> dict:
    """Load the sample order set for the caller (only if they have none)."""
    _require_db()
    return {"orders": OrderRepository().seed_samples(uid)}


@router.get("/{order_id}")
def get_order(order_id: str, uid: str = Depends(current_uid)) -> dict:
    _require_db()
    doc = OrderRepository().get(uid, order_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found.")
    return doc


@router.put("/{order_id}")
def upsert_order(
    order_id: str, body: OrderBody, uid: str = Depends(current_uid)
) -> dict:
    _require_db()
    return OrderRepository().upsert(uid, order_id, body.model_dump())


@router.post("/{order_id}/cancel")
def cancel_order(
    order_id: str, body: CancelBody, uid: str = Depends(current_uid)
) -> dict:
    _require_db()
    doc = OrderRepository().cancel(uid, order_id, body.reason)
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found.")
    return doc


@router.post("/{order_id}/alteration")
def request_alteration(
    order_id: str, body: AlterationBody, uid: str = Depends(current_uid)
) -> dict:
    _require_db()
    doc = OrderRepository().request_alteration(uid, order_id, body.description)
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found.")
    return doc


@router.delete("/{order_id}")
def delete_order(order_id: str, uid: str = Depends(current_uid)) -> dict:
    _require_db()
    if not OrderRepository().delete(uid, order_id):
        raise HTTPException(status_code=404, detail="Order not found.")
    return {"deleted": True}
