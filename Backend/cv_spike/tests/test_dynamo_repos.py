"""DynamoDB repository + blob-store tests (moto-mocked, no real AWS).

Covers the Mongo->DynamoDB migration: Decimal round-tripping, user scoping,
list/sort, ground-truth updates, calibration upsert/clear, vest persistence, and
both blob backends (disk + S3).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("moto")


def _insert(repo, **over):
    from api.db.scans import ScanRepository

    scan_id = over.pop("scan_id", None) or ScanRepository.new_id()
    kwargs = dict(
        scan_id=scan_id,
        mode="height",
        height_cm=165.0,
        weight_kg=60.0,
        prefer="photo",
        measurements={"girths_cm": {"bust": 90.5, "waist": 70.2}},
        manifest={"version": 1, "views": ["front"]},
        mesh_included=False,
        bundle_bytes=b"PK\x03\x04-zip-bytes",
        bundle_filename=f"{scan_id}.zip",
        photo_files=None,
        metadata={"subject_label": "subj-1"},
        user_id="user-1",
    )
    kwargs.update(over)
    return repo.insert_scan(**kwargs)


def test_scan_roundtrip_disk_blobs(aws_backend, tmp_path):
    from api.db.scans import ScanRepository

    repo = ScanRepository()
    photo = tmp_path / "front.jpg"
    photo.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")

    doc = _insert(repo, photo_files={"front": photo})
    sid = doc["scan_id"]

    # float survives the Decimal round-trip; metadata carried through.
    assert doc["measurements"]["girths_cm"]["bust"] == 90.5
    assert isinstance(doc["measurements"]["girths_cm"]["bust"], float)
    assert doc["subject_label"] == "subj-1"
    # serialized photo descriptor hides the absolute disk path.
    assert doc["photos"]["front"]["storage"] == "disk"
    assert "path" not in doc["photos"]["front"]

    got = repo.get_scan(sid, user_id="user-1")
    assert got["height_cm"] == 165.0
    # ownership enforced.
    assert repo.get_scan(sid, user_id="someone-else") is None

    # bundle + photo stream back.
    bundle = repo.open_bundle(sid, user_id="user-1")
    assert bundle is not None
    path_or_stream, fname, size = bundle
    assert size == len(b"PK\x03\x04-zip-bytes")
    assert Path(path_or_stream).read_bytes() == b"PK\x03\x04-zip-bytes"

    pic = repo.open_photo(sid, "front", user_id="user-1")
    assert pic is not None
    stream, pic_name, ctype = pic
    assert ctype == "image/jpeg"
    assert stream.read() == b"\xff\xd8\xff\xe0fake-jpeg-bytes"


def test_list_sorted_and_scoped(aws_backend):
    from api.db.scans import ScanRepository

    repo = ScanRepository()
    a = _insert(repo, user_id="user-1")
    b = _insert(repo, user_id="user-1")
    _insert(repo, user_id="user-2")

    mine = repo.list_scans(user_id="user-1")
    assert {s["scan_id"] for s in mine} == {a["scan_id"], b["scan_id"]}
    # newest first (created_at desc).
    assert mine[0]["created_at"] >= mine[-1]["created_at"]
    assert repo.list_scans(user_id="nobody") == []
    assert len(repo.list_scans()) == 3  # no scope -> all


def test_update_ground_truth(aws_backend):
    from api.db.scans import ScanRepository

    repo = ScanRepository()
    doc = _insert(repo)
    sid = doc["scan_id"]

    updated = repo.update_ground_truth(sid, {"bust": 91.0, "waist": 0}, user_id="user-1")
    assert updated["ground_truth_cm"] == {"bust": 91.0}  # non-positive dropped
    cmp = updated["ground_truth_comparison"]["bust"]
    assert cmp["predicted_cm"] == 90.5
    assert cmp["tape_cm"] == 91.0
    assert cmp["error_cm"] == 0.5
    # missing scan / wrong owner -> None.
    assert repo.update_ground_truth("missing", {"bust": 90}, user_id="user-1") is None


def test_calibration_repo(aws_backend):
    from api.db.calibration import CalibrationRepository
    from pipeline.measure.calibration import CalibrationProfile

    repo = CalibrationRepository()
    assert repo.get_global() is None
    assert repo.clear_global() is False

    prof = CalibrationProfile(name="global", scale=1.08, offset_cm=-2.5, anchors_cm={"waist": 72.0})
    repo.save_global(prof, training_scans=4, training_pairs=11)

    loaded = repo.get_global()
    assert loaded.scale == 1.08
    assert loaded.anchors_cm["waist"] == 72.0
    meta = repo.get_global_meta()
    assert meta["training_scans"] == 4 and meta["training_pairs"] == 11

    assert repo.clear_global() is True
    assert repo.get_global() is None


def test_vest_persist_and_ground_truth(aws_backend, monkeypatch):
    import api.services.vest_service as vest

    # avoid running the CV measurement: stub it out.
    monkeypatch.setattr(vest, "measure_vest_views", None, raising=False)
    table = vest.get_table(vest.VEST_TABLE)
    sid = "vest_test_1"
    table.put_item(
        Item=vest.to_item(
            {
                "scan_id": sid,
                "kind": "vest",
                "created_at": "2026-06-24T00:00:00+00:00",
                "measurement": {"girths_in": {"bust": 36.0}, "calibration_factor": 1.04},
                "photos": {"front": {"storage": "disk", "path": "/tmp/x.jpg"}},
            }
        )
    )

    got = vest.get_vest_scan(sid)
    assert got["measurement"]["girths_in"]["bust"] == 36.0
    assert "photos" not in got  # photos stripped from public view

    updated = vest.save_vest_ground_truth(sid, {"bust_in": 35.5})
    assert updated["ground_truth_in"]["bust_in"] == 35.5
    assert vest.save_vest_ground_truth("does-not-exist", {"bust_in": 30}) is None

    assert any(s["scan_id"] == sid for s in vest.list_vest_scans())


def test_persona_gender_roundtrip(aws_backend):
    from api.db.personas import PersonaRepository

    repo = PersonaRepository()
    male = repo.upsert(
        "user-1", "p_male", name="Dad", label="Father",
        gender="male", measurements={"chest": 100.0},
    )
    assert male["gender"] == "male"

    female = repo.upsert(
        "user-1", "p_fem", name="Me", label="Me", measurements={"bust": 90.0},
    )
    assert female["gender"] == "female"  # default

    # round-trips through storage + ownership scoping
    listed = {p["id"]: p for p in repo.list("user-1")}
    assert listed["p_male"]["gender"] == "male"
    assert listed["p_fem"]["gender"] == "female"


def test_order_garment_roundtrip(aws_backend):
    from api.db.orders import OrderRepository

    repo = OrderRepository()
    made = repo.create("user-1", {"garment": "Sherwani", "category": "active"})
    assert made["garment"] == "Sherwani"

    # default garment when omitted (back-compat with pre-garment orders)
    plain = repo.create("user-1", {"category": "active"})
    assert plain["garment"] == "Blouse"

    got = repo.get("user-1", made["id"])
    assert got["garment"] == "Sherwani"


def test_scan_roundtrip_s3_blobs(aws_backend, monkeypatch, tmp_path):
    """Same flow as disk, but blobs go to S3 (the production path)."""
    import boto3

    import api.storage.photo_store as photo_store
    from api.db.scans import ScanRepository

    bucket = "dsv-test-bucket"
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=bucket)
    monkeypatch.setattr(photo_store, "PHOTO_STORAGE", "s3")
    monkeypatch.setattr(photo_store, "SCAN_STORAGE_BACKEND", "s3")
    monkeypatch.setattr(photo_store, "S3_BUCKET", bucket)

    repo = ScanRepository()
    photo = tmp_path / "front.jpg"
    photo.write_bytes(b"\xff\xd8\xff\xe0s3-jpeg")
    doc = _insert(repo, photo_files={"front": photo})
    sid = doc["scan_id"]

    assert doc["bundle_storage"] == "s3"
    assert doc["photos"]["front"]["storage"] == "s3"
    assert doc["photos"]["front"]["s3_key"].endswith("front.jpg")

    bundle = repo.open_bundle(sid, user_id="user-1")
    assert bundle is not None
    stream, fname, size = bundle
    assert stream.read() == b"PK\x03\x04-zip-bytes"

    pic = repo.open_photo(sid, "front", user_id="user-1")
    assert pic is not None
    assert pic[0].read() == b"\xff\xd8\xff\xe0s3-jpeg"
