"""Beta bundle builder (no MongoDB)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from pipeline.measure.bundle_export import build_beta_bundle

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "tests" / "fixtures" / "profiles"


@pytest.mark.slow
def test_build_beta_bundle(tmp_path):
    front = REFS / "front" / "dummy_female_01.jpg"
    back = REFS / "back" / "dummy_female_01.jpg"
    side = REFS / "side" / "dummy_female_01.jpg"
    for p in (front, back, side):
        assert p.is_file(), p

    work = tmp_path / "contents"
    result, zip_path, manifest = build_beta_bundle(
        scan_id="test-scan",
        work_dir=work,
        front=front,
        back=back,
        side=side,
        height_cm=165.0,
        weight_kg=60.0,
        prefer="photo",
    )
    assert zip_path.is_file()
    assert result.girths_cm
    assert manifest["bundle_version"]

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "measurements.json" in names
        assert any(n.startswith("photos/") for n in names)
        m = json.loads(zf.read("manifest.json"))
        assert m["scan_id"] == "test-scan"
