"""Vest ChArUco beta endpoint + measurement tests (no MongoDB / no asset photos needed)."""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from pipeline.measure import vest_charuco
from pipeline.measure.vest_charuco import (
    IDS_PER_BOARD,
    VEST_CALIBRATION_FACTOR,
    VEST_DICT,
    VEST_MARKER_NAMES,
    circular_girth_cm,
    detect_markers,
    shoulder_to_shoulder_cm,
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    from api.main import app

    return TestClient(app)


def _render_board(id_offset: int, square_px: int = 90) -> np.ndarray:
    """Render one 5x4 vest ChArUco board with marker ids starting at id_offset."""
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, VEST_DICT))
    ids = np.arange(id_offset, id_offset + (5 * 4) // 2, dtype=np.int32)
    board = cv2.aruco.CharucoBoard((5, 4), 0.012, 0.009, d, ids)
    img = board.generateImage((5 * square_px, 4 * square_px), marginSize=square_px // 2)
    return img  # grayscale


def _jpeg_bytes(img_bgr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", img_bgr)
    assert ok
    return buf.tobytes()


def test_health_reports_vest_beta(client):
    body = client.get("/health").json()
    assert body["vest_beta"]["dict"] == VEST_DICT
    assert body["vest_beta"]["calibration_factor"] == VEST_CALIBRATION_FACTOR


def test_detect_markers_maps_id_block_to_landmark():
    # FB (front bust) occupies ids 20..29 -> block index 2.
    fb_offset = VEST_MARKER_NAMES.index("FB") * IDS_PER_BOARD
    gray = _render_board(fb_offset)
    det = detect_markers(gray)
    assert "FB" in det
    assert det["FB"]["px_per_mm"] > 0


def test_circular_girth_applies_calibration():
    # width 24.26 cm -> circular circumference 76.2 cm, x1.04 calibration.
    assert circular_girth_cm(24.26) == pytest.approx(np.pi * 24.26 * VEST_CALIBRATION_FACTOR)


def test_shoulder_to_shoulder_from_pose(monkeypatch):
    """Ported algorithm: shoulder = ||L_SHO - R_SHO|| / scale, in cm."""
    # 2 px/mm => 20 px/cm. Shoulders 800 px apart => 40 cm.
    det = {"BSH_L": {"px_per_mm": 2.0}, "BSH_R": {"px_per_mm": 2.0}}
    monkeypatch.setattr(
        vest_charuco,
        "_pose_landmarks",
        lambda _img: {"l_shoulder": [100, 500], "r_shoulder": [900, 500]},
    )
    cm, warn = shoulder_to_shoulder_cm(np.zeros((1000, 1000, 3), np.uint8), det)
    assert cm == pytest.approx(40.0)
    assert warn is None


def test_shoulder_to_shoulder_flags_implausible(monkeypatch):
    det = {"BSH_L": {"px_per_mm": 2.0}, "BSH_R": {"px_per_mm": 2.0}}
    # 1600 px apart => 80 cm, outside the typical adult range.
    monkeypatch.setattr(
        vest_charuco,
        "_pose_landmarks",
        lambda _img: {"l_shoulder": [100, 500], "r_shoulder": [1700, 500]},
    )
    cm, warn = shoulder_to_shoulder_cm(np.zeros((1000, 2000, 3), np.uint8), det)
    assert cm == pytest.approx(80.0)
    assert warn == "shoulder_out_of_typical_range"


def test_shoulder_to_shoulder_no_pose(monkeypatch):
    monkeypatch.setattr(vest_charuco, "_pose_landmarks", lambda _img: None)
    cm, warn = shoulder_to_shoulder_cm(np.zeros((10, 10, 3), np.uint8), {})
    assert cm is None
    assert warn == "pose_not_detected_for_shoulder"


def test_vest_endpoint_requires_front(client):
    assert client.post("/v1/vest", data={"collector_id": "t"}).status_code == 422


def test_vest_endpoint_runs_without_markers(client):
    """A photo with no markers still returns 200 with a warning (no crash, no store)."""
    blank = np.full((1000, 800, 3), 240, np.uint8)
    res = client.post(
        "/v1/vest",
        files={"front": ("front.jpg", _jpeg_bytes(blank), "image/jpeg")},
        data={"collector_id": "tailor_test", "bust_in": "38.5"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["kind"] == "vest"
    assert body["measurement"]["measurements_reliable"] is False
    assert "no_front_markers_detected" in body["measurement"]["warnings"]
    assert body["ground_truth_in"] == {"bust_in": 38.5}


def test_partial_bands_when_one_marker_missing():
    """A missing bust marker still yields waist + hip (graceful degradation)."""
    import numpy as np

    from pipeline.measure.vest_charuco import VEST_MARKER_NAMES, measure_vest_front

    # Compose a canvas with FW (waist) + FH (hip) boards but NO FB (bust).
    canvas = np.full((1600, 1200, 3), 235, np.uint8)

    def place(name: str, cy: int) -> None:
        off = VEST_MARKER_NAMES.index(name) * IDS_PER_BOARD
        board = cv2.cvtColor(_render_board(off, square_px=70), cv2.COLOR_GRAY2BGR)
        h, w = board.shape[:2]
        x = (canvas.shape[1] - w) // 2
        canvas[cy:cy + h, x:x + w] = board

    place("FW", 620)
    place("FH", 1040)
    res = measure_vest_front(canvas)
    assert "FB" not in res.markers_found
    assert "bust_marker_not_detected" in res.warnings
    # waist/hip markers detected -> front view recognized, not a hard failure
    assert "front" in res.views
