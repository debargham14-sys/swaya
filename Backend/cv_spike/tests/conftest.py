import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def aws_backend(monkeypatch, tmp_path):
    """In-process DynamoDB + S3 (moto) with the four tables created and blobs on disk.

    Lets DB-backed tests run offline with no real AWS / DynamoDB Local. Blob storage
    defaults to a temp disk dir; tests that exercise the S3 path opt in by patching
    ``photo_store`` globals (see ``test_dynamo_repos``).
    """
    pytest.importorskip("moto")
    from moto import mock_aws

    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN"):
        monkeypatch.setenv(key, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    with mock_aws():
        import api.db.dynamo as dynamo
        import api.storage.photo_store as photo_store

        dynamo._resource.cache_clear()
        dynamo._last_error = None
        dynamo.ensure_tables()

        monkeypatch.setattr(photo_store, "SCAN_STORAGE_DIR", tmp_path / "scans")
        monkeypatch.setattr(photo_store, "PHOTO_STORAGE", "disk")
        monkeypatch.setattr(photo_store, "SCAN_STORAGE_BACKEND", "disk")
        try:
            yield
        finally:
            dynamo._resource.cache_clear()
