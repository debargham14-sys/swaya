"""Grid-cell shoulder thread (ported from ImageToMeasurements 1cm branch).

Deterministic synthetic-grid tests — no pose model, no ChArUco render needed.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from pipeline.measure.vest_shoulder_grid import (
    GRID_CM,
    arc_cm,
    measure_back_shoulder,
    thread_cm,
    vertical_lines_at,
)

PPC = 20.0           # px per cm
CELL = PPC * GRID_CM  # px per 1-inch grid cell (= 50.8)


def _grid_image(w: int = 900, h: int = 400, n_lines: int = 15, x0: int = 60):
    """White panel with evenly spaced thin dark vertical grid lines (1 inch apart)."""
    img = np.full((h, w, 3), 245, np.uint8)
    xs = [int(round(x0 + i * CELL)) for i in range(n_lines)]
    for x in xs:
        cv2.line(img, (x, 0), (x, h), (40, 40, 40), 2)
    return img, xs


def test_vertical_lines_detected():
    img, xs = _grid_image()
    mask = np.ones(img.shape[:2], np.uint8)
    found = vertical_lines_at(img, 200, mask, PPC)
    assert len(found) >= len(xs) - 2  # nearly all lines recovered


def test_arc_cm_counts_whole_inches():
    img, xs = _grid_image()
    mask = np.ones(img.shape[:2], np.uint8)
    lines = vertical_lines_at(img, 200, mask, PPC)
    r = arc_cm(xs[2], xs[7], lines, PPC)  # span exactly 5 cells
    assert r["used"] == "grid"
    assert r["n_cells"] == 5
    assert r["grid_cm"] == pytest.approx(5 * GRID_CM, abs=0.4)


def test_arc_cm_robust_to_a_missing_line():
    """A dropped interior line becomes one 2-cell gap, so the total is preserved."""
    img, xs = _grid_image()
    mask = np.ones(img.shape[:2], np.uint8)
    lines = vertical_lines_at(img, 200, mask, PPC)
    lines = [x for x in lines if abs(x - xs[5]) > 5]  # remove the line at xs[5]
    r = arc_cm(xs[2], xs[7], lines, PPC)
    assert r["n_cells"] == 5
    assert r["grid_cm"] == pytest.approx(5 * GRID_CM, abs=0.4)


def test_thread_includes_vertical_slope():
    img, xs = _grid_image()
    mask = np.ones(img.shape[:2], np.uint8)
    pL, pR = (xs[2], 200), (xs[7], 220)  # 20 px drop == 1 cm
    out = thread_cm(img, pL, pR, mask, PPC)
    assert out["n_cells"] == 5
    assert out["dv_cm"] == pytest.approx(1.0, abs=0.01)
    assert out["thread_cm"] == pytest.approx(np.hypot(5 * GRID_CM, 1.0), abs=0.4)
    # surface arc exceeds the flat straight distance across a curved/sloped span
    assert out["thread_cm"] >= out["straight_cm"] - 0.5


def test_measure_back_shoulder_end_to_end():
    img, xs = _grid_image(w=900, h=400)
    mask = np.zeros(img.shape[:2], np.uint8)
    mask[150:240, xs[2]:xs[10]] = 1  # vest spans 8 cells at shoulder level
    det = {
        "BSH_L": {"center": np.array([xs[2], 195.0]), "px_per_mm": PPC / 10},
        "BSH_R": {"center": np.array([xs[10], 195.0]), "px_per_mm": PPC / 10},
    }
    out = measure_back_shoulder(img, det, vest_mask=mask)
    assert out is not None
    assert out["ppc"] == pytest.approx(PPC)
    assert out["n_cells"] == 8
    assert out["thread_cm"] == pytest.approx(8 * GRID_CM, abs=1.0)


def test_measure_back_shoulder_none_without_silhouette():
    img, _ = _grid_image()
    empty = np.zeros(img.shape[:2], np.uint8)
    det = {"BSH_L": {"center": np.array([100.0, 200.0]), "px_per_mm": 2.0},
           "BSH_R": {"center": np.array([500.0, 200.0]), "px_per_mm": 2.0}}
    assert measure_back_shoulder(img, det, vest_mask=empty) is None
