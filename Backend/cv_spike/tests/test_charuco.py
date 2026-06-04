"""Stage-1 calibration tests: ChArUco/ArUco detection + px<->mm homography."""

from __future__ import annotations

import numpy as np

from pipeline.qc import charuco
from pipeline.qc.framework_spec import STANDARD_A1 as S
from qc_synth import MARGIN_PX, make_framework_image


def test_detects_four_corner_fiducials():
    img, _ = make_framework_image(px_per_mm=2.0)
    calib = charuco.calibrate(img, S)
    assert calib.corners_found == 4
    assert not calib.needs_retake
    assert calib.method == "homography"
    assert calib.detected_ids == [0, 1, 2, 3]


def test_homography_recovers_mm_coordinates():
    px_per_mm = 2.0
    img, _ = make_framework_image(px_per_mm=px_per_mm)
    calib = charuco.calibrate(img, S)

    # The synthetic mapping is px = mm * px_per_mm + MARGIN_PX, so check that
    # px_to_mm inverts it within a fraction of a millimetre.
    for mm_pt in [(50.0, 50.0), (297.0, 420.0), (544.0, 791.0)]:
        px = np.array([[mm_pt[0] * px_per_mm + MARGIN_PX, mm_pt[1] * px_per_mm + MARGIN_PX]])
        got = calib.px_to_mm(px)[0]
        assert abs(got[0] - mm_pt[0]) < 1.0
        assert abs(got[1] - mm_pt[1]) < 1.0


def test_mm_per_px_estimate():
    img, _ = make_framework_image(px_per_mm=2.0)
    calib = charuco.calibrate(img, S)
    # 2 px per mm -> 0.5 mm per px
    assert abs(calib.mm_per_px - 0.5) < 0.02


def test_blank_image_needs_retake():
    blank = np.full((400, 400, 3), 232, np.uint8)
    calib = charuco.calibrate(blank, S)
    assert calib.corners_found == 0
    assert calib.needs_retake
    assert calib.H_px_to_mm is None
