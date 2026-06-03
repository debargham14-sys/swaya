"""MongoDB access for DSV scan persistence."""

from api.db.mongo import get_db, mongo_available
from api.db.scans import ScanRepository

__all__ = ["ScanRepository", "get_db", "mongo_available"]
