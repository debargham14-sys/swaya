"""Persist the learned tape->photo calibration profile in DynamoDB."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from api.db.dynamo import from_item, get_table, to_item
from pipeline.measure.calibration import CalibrationProfile

GLOBAL_PROFILE_ID = "global"


class CalibrationRepository:
    TABLE = "calibration"

    def __init__(self) -> None:
        self._table = get_table(self.TABLE)

    def _get(self) -> dict[str, Any] | None:
        item = self._table.get_item(Key={"id": GLOBAL_PROFILE_ID}).get("Item")
        return from_item(item) if item else None

    def get_global(self) -> CalibrationProfile | None:
        doc = self._get()
        if not doc or "profile" not in doc:
            return None
        return CalibrationProfile.from_dict(doc["profile"])

    def get_global_meta(self) -> dict[str, Any] | None:
        doc = self._get()
        if not doc:
            return None
        return {
            "training_scans": int(doc.get("training_scans", 0)),
            "training_pairs": int(doc.get("training_pairs", 0)),
            "updated_at": doc.get("updated_at"),
        }

    def save_global(
        self,
        profile: CalibrationProfile,
        *,
        training_scans: int,
        training_pairs: int,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._table.put_item(
            Item=to_item(
                {
                    "id": GLOBAL_PROFILE_ID,
                    "profile": profile.to_dict(),
                    "training_scans": training_scans,
                    "training_pairs": training_pairs,
                    "updated_at": now,
                }
            )
        )

    def clear_global(self) -> bool:
        resp = self._table.delete_item(
            Key={"id": GLOBAL_PROFILE_ID}, ReturnValues="ALL_OLD"
        )
        return bool(resp.get("Attributes"))
