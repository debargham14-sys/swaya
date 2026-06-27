"""DynamoDB access for DSV scan persistence."""

from api.db.dynamo import dynamo_available, dynamo_last_error, ensure_tables, get_table
from api.db.scans import ScanRepository

__all__ = [
    "ScanRepository",
    "get_table",
    "dynamo_available",
    "dynamo_last_error",
    "ensure_tables",
]
