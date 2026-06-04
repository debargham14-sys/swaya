"""
Build a beta download bundle: manifest + measurements + photos + optional body.obj.
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2

from api.settings import BUNDLE_TRY_MESH, BUNDLE_VERSION
from pipeline.measure import mesh_measure, smpl_backend
from pipeline.measure.measure_engine import EngineResult, measure


def _try_export_body_obj(front_path: Path, height_cm: float, dest: Path, prefer: str) -> tuple[bool, str | None]:
    if not BUNDLE_TRY_MESH:
        return False, "mesh_export_disabled"
    try:
        img = cv2.imread(str(front_path), cv2.IMREAD_COLOR)
        if img is None:
            return False, "front_image_unreadable"
        mesh, backend = smpl_backend.recover_mesh(
            image_bgr=img,
            prefer=prefer if prefer not in ("photo", "auto") else "four_d_humans",
        )
        scaled, _ = mesh_measure.scale_mesh_to_height(mesh, height_cm)
        scaled.export(str(dest))
        return True, backend
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def build_beta_bundle(
    *,
    scan_id: str,
    work_dir: Path,
    front: Path,
    back: Path,
    side: Path,
    height_cm: float,
    weight_kg: float | None,
    prefer: str,
    ref_kind: str | None = None,
    ref_marker_mm: float = 50.0,
) -> tuple[EngineResult, Path, dict[str, Any]]:
    """Run measurement, write bundle zip under work_dir; return result + zip path + manifest."""
    work_dir.mkdir(parents=True, exist_ok=True)
    photos_dir = work_dir / "photos"
    photos_dir.mkdir(exist_ok=True)

    for view, src in ("front", front), ("back", back), ("side", side):
        ext = src.suffix or ".jpg"
        dest = photos_dir / f"{view}{ext}"
        dest.write_bytes(src.read_bytes())

    import logging
    import time

    _log = logging.getLogger("swaya.measure")
    _t = time.perf_counter()
    _log.info("bundle %s: measurement start (prefer=%s)", scan_id, prefer)
    result = measure(
        height_cm=height_cm,
        weight_kg=weight_kg,
        front=front,
        back=back,
        side=side,
        prefer=prefer,
        ref_kind=ref_kind,
        ref_marker_mm=ref_marker_mm,
    )

    _log.info("bundle %s: measurement done in %.1fs", scan_id, time.perf_counter() - _t)

    measurements_path = work_dir / "measurements.json"
    measurements_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

    mesh_path = work_dir / "body.obj"
    mesh_ok, mesh_note = _try_export_body_obj(front, height_cm, mesh_path, prefer)

    manifest: dict[str, Any] = {
        "bundle_version": BUNDLE_VERSION,
        "scan_id": scan_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "format": "dsv-beta-bundle",
        "description": "DSV beta export: measurements, capture photos, optional SMPL body mesh.",
        "files": {
            "manifest.json": "This file",
            "measurements.json": "Girths, BMI, backend, warnings",
            "photos/front": "Front capture",
            "photos/back": "Back capture",
            "photos/side": "Side capture",
        },
        "mesh": {
            "included": mesh_ok,
            "path": "body.obj" if mesh_ok else None,
            "note": mesh_note if not mesh_ok else None,
            "backend": mesh_note if mesh_ok else None,
        },
        "measurement_backend": result.backend,
    }
    manifest_path = work_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    readme = work_dir / "README.txt"
    readme.write_text(
        f"DSV Beta Bundle\nscan_id={scan_id}\n\n"
        f"Open body.obj in Blender/MeshLab (included={mesh_ok}).\n"
        f"measurements.json has bust/waist/hip in cm.\n",
        encoding="utf-8",
    )

    zip_path = work_dir.parent / f"{scan_id}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in work_dir.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=path.relative_to(work_dir).as_posix())

    return result, zip_path, manifest
