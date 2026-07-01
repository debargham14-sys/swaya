"""DynamoDB client helpers (replaces the former MongoDB layer).

Four single-key tables hold the JSON metadata that Mongo collections used to:
``scans``, ``calibration``, ``vest_scans``, ``vest_calibration`` — each named
``{DYNAMO_TABLE_PREFIX}_{logical}``. Binary blobs (bundle ZIPs, raw photos)
never live here (DynamoDB items are capped at 400 KB) — see ``storage.photo_store``.

The service degrades gracefully when DynamoDB is unreachable, mirroring the old
``mongo_available()`` contract so routes/services can keep their guards.
"""

from __future__ import annotations

import math
from decimal import Decimal
from functools import lru_cache
from typing import Any

from api.settings import AWS_REGION, DYNAMO_ENDPOINT_URL, DYNAMO_TABLE_PREFIX

# logical table name -> partition-key attribute. Physical name is prefixed.
# MUST stay in sync with infra/terraform/main.tf local.dynamo_tables.
TABLES: dict[str, str] = {
    "scans": "scan_id",
    "calibration": "id",
    "vest_scans": "scan_id",
    "vest_calibration": "id",
    "users": "uid",
    "personas": "persona_id",
    "orders": "order_id",
    "designers": "designer_id",
    "collab_sessions": "session_id",
    "collab_messages": "message_id",
}

_last_error: str | None = None


def physical_name(logical: str) -> str:
    return f"{DYNAMO_TABLE_PREFIX}_{logical}"


@lru_cache(maxsize=1)
def _resource():
    import boto3

    kwargs: dict[str, Any] = {"region_name": AWS_REGION}
    if DYNAMO_ENDPOINT_URL:
        # Local DynamoDB / moto need an endpoint and (dummy) creds.
        kwargs["endpoint_url"] = DYNAMO_ENDPOINT_URL
    return boto3.resource("dynamodb", **kwargs)


def get_table(logical: str):
    if logical not in TABLES:
        raise KeyError(f"unknown table {logical!r}")
    return _resource().Table(physical_name(logical))


def dynamo_available() -> bool:
    """True when the DynamoDB endpoint is reachable and the scans table exists."""
    global _last_error
    try:
        get_table("scans").table_status  # cheap DescribeTable round-trip
        return True
    except Exception as exc:  # noqa: BLE001
        _last_error = str(exc)
        return False


def dynamo_last_error() -> str | None:
    return _last_error


def ensure_tables() -> None:
    """Create any missing tables (idempotent). For local dev / tests / first boot.

    Production tables are provisioned by Terraform; this is a no-op once they exist.
    """
    client = _resource().meta.client
    existing = set(client.list_tables().get("TableNames", []))
    for logical, key_attr in TABLES.items():
        name = physical_name(logical)
        if name in existing:
            continue
        client.create_table(
            TableName=name,
            KeySchema=[{"AttributeName": key_attr, "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": key_attr, "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.get_waiter("table_exists").wait(TableName=name)


# --- (de)serialization ------------------------------------------------------
# DynamoDB's document model accepts only Decimal numbers (no float) and rejects
# NaN/Inf. These walk nested dicts/lists converting on the way in and out.

def to_item(obj: Any) -> Any:
    """Python value -> DynamoDB-safe value (float->Decimal, non-finite->None)."""
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return Decimal(str(obj)) if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: to_item(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_item(v) for v in obj]
    return obj


def from_item(obj: Any) -> Any:
    """DynamoDB value -> plain Python (Decimal->int/float)."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: from_item(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [from_item(v) for v in obj]
    return obj
