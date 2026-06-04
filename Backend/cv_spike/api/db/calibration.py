"""Persist learned tape→photo calibration profile in MongoDB."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from api.db.mongo import get_db
from pipeline.measure.calibration import CalibrationProfile

GLOBAL_PROFILE_ID = "global"


class CalibrationRepository:
    COLLECTION = "calibration_profiles"

    def __init__(self) -> None:
        self._col = get_db()[self.COLLECTION]

    def get_global(self) -> CalibrationProfile | None:
        doc = self._col.find_one({"_id": GLOBAL_PROFILE_ID})
        if not doc or "profile" not in doc:
            return None
        return CalibrationProfile.from_dict(doc["profile"])

    def get_global_meta(self) -> dict[str, Any] | None:
        doc = self._col.find_one({"_id": GLOBAL_PROFILE_ID})
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
        now = datetime.now(timezone.utc)
        self._col.update_one(
            {"_id": GLOBAL_PROFILE_ID},
            {
                "$set": {
                    "profile": profile.to_dict(),
                    "training_scans": training_scans,
                    "training_pairs": training_pairs,
                    "updated_at": now,
                }
            },
            upsert=True,
        )
