"""Create scans: measure, bundle, persist to MongoDB (GridFS or disk)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from api.db.calibration import CalibrationRepository
from api.db.scans import ScanRepository
from api.services.calibration_service import apply_to_engine_result, refresh_scan_after_ground_truth
from pipeline.measure.bundle_export import build_beta_bundle


class ScanServiceError(Exception):
    pass


class ScanService:
    def __init__(self, repo: ScanRepository | None = None) -> None:
        self._repo = repo or ScanRepository()

    def create_scan_from_paths(
        self,
        *,
        front: Path,
        back: Path,
        side: Path,
        height_cm: float,
        weight_kg: float | None,
        mode: str = "height",
        prefer: str = "photo",
        ref_kind: str | None = None,
        ref_marker_mm: float = 50.0,
        subject_label: str | None = None,
        collector_id: str | None = None,
        consent_given: bool | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        scan_id = ScanRepository.new_id()

        with tempfile.TemporaryDirectory(prefix="dsv_scan_") as tmp:
            work_dir = Path(tmp) / "bundle_contents"
            result, zip_path, manifest = build_beta_bundle(
                scan_id=scan_id,
                work_dir=work_dir,
                front=front,
                back=back,
                side=side,
                height_cm=height_cm,
                weight_kg=weight_kg or 0.0,
                prefer=prefer,
                ref_kind=ref_kind,
                ref_marker_mm=ref_marker_mm,
            )
            result = apply_to_engine_result(result)
            bundle_bytes = zip_path.read_bytes()
            bundle_filename = f"{scan_id}.zip"

        measurements = result.to_dict()
        if result.calibration_profile:
            meta = CalibrationRepository().get_global_meta()
            if meta:
                measurements["calibration_training_scans"] = meta.get("training_scans")
        measurements["mode"] = mode
        measurements["scan_id"] = scan_id

        metadata: dict[str, Any] = {}
        if subject_label:
            metadata["subject_label"] = subject_label
        if collector_id:
            metadata["collector_id"] = collector_id
        if consent_given is not None:
            metadata["consent_given"] = consent_given
        if notes:
            metadata["notes"] = notes

        doc = self._repo.insert_scan(
            scan_id=scan_id,
            mode=mode,
            height_cm=height_cm,
            weight_kg=weight_kg,
            prefer=prefer,
            measurements=measurements,
            manifest=manifest,
            mesh_included=bool(manifest.get("mesh", {}).get("included")),
            bundle_bytes=bundle_bytes,
            bundle_filename=bundle_filename,
            photo_files={"front": front, "back": back, "side": side},
            metadata=metadata or None,
        )
        doc["download_url"] = f"/v1/scans/{scan_id}/bundle"
        doc["photo_urls"] = self._photo_urls(scan_id, doc)
        return doc

    def get_scan(self, scan_id: str) -> dict[str, Any] | None:
        doc = self._repo.get_scan(scan_id)
        if doc:
            sid = doc.get("scan_id") or scan_id
            doc["download_url"] = f"/v1/scans/{sid}/bundle"
            doc["photo_urls"] = self._photo_urls(sid, doc)
        return doc

    def list_scans(self, limit: int = 30) -> list[dict[str, Any]]:
        items = self._repo.list_scans(limit=limit)
        for doc in items:
            sid = doc.get("scan_id")
            if sid:
                doc["download_url"] = f"/v1/scans/{sid}/bundle"
                doc["photo_urls"] = self._photo_urls(sid, doc)
        return items

    def open_bundle(self, scan_id: str):
        return self._repo.open_bundle(scan_id)

    def open_photo(self, scan_id: str, view: str):
        return self._repo.open_photo(scan_id, view)

    def save_ground_truth(self, scan_id: str, ground_truth_cm: dict[str, float]) -> dict[str, Any] | None:
        doc = self._repo.update_ground_truth(scan_id, ground_truth_cm)
        if not doc:
            return None
        was_calibrated = bool((doc.get("measurements") or {}).get("calibration_profile"))
        doc = refresh_scan_after_ground_truth(scan_id) or doc
        now_calibrated = bool((doc.get("measurements") or {}).get("calibration_profile"))
        doc["calibration_updated"] = now_calibrated and (
            not was_calibrated or bool(doc.get("ground_truth_comparison"))
        )
        doc["download_url"] = f"/v1/scans/{scan_id}/bundle"
        doc["photo_urls"] = self._photo_urls(scan_id, doc)
        return doc

    @staticmethod
    def _photo_urls(scan_id: str, doc: dict[str, Any]) -> dict[str, str]:
        urls: dict[str, str] = {}
        photos = doc.get("photos") or {}
        for view in ("front", "back", "side"):
            meta = photos.get(view) if isinstance(photos, dict) else None
            if isinstance(meta, dict) and meta.get("s3_url"):
                urls[view] = meta["s3_url"]
            else:
                urls[view] = f"/v1/scans/{scan_id}/photos/{view}"
        return urls


def process_uploaded_scan(
    paths: dict[str, Path],
    height_cm: float,
    weight_kg: float | None,
    mode: str,
    prefer: str,
    ref_kind: str | None,
    ref_marker_mm: float,
    *,
    subject_label: str | None = None,
    collector_id: str | None = None,
    consent_given: bool | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Convenience for API layer."""
    return ScanService().create_scan_from_paths(
        front=paths["front"],
        back=paths["back"],
        side=paths["side"],
        height_cm=height_cm,
        weight_kg=weight_kg,
        mode=mode,
        prefer=prefer,
        ref_kind=ref_kind,
        ref_marker_mm=ref_marker_mm,
        subject_label=subject_label,
        collector_id=collector_id,
        consent_given=consent_given,
        notes=notes,
    )
