"""Slice-sweep and body-shape girth tests."""

from __future__ import annotations

import numpy as np

from pipeline.measure.body_shape import detect_loose_top, levels_from_body_shape
from pipeline.measure.slice_measure import SliceSample, levels_from_sweep, scan_torso_slices


def _synthetic_masks(h=800, w=400):
    front = np.zeros((h, w), np.uint8)
    side = np.zeros((h, w), np.uint8)
    sh, hip = 200, 520
    for y in range(sh, h):
        frac = (y - sh) / max(1, hip - sh)
        if y <= hip:
            fw = int(40 + 20 * abs(frac - 0.65))
        else:
            fw = int(40 + 80 * (y - hip) / 200)
        front[y, w // 2 - fw : w // 2 + fw] = 255
        sd = 28 if y <= hip else 28 + (y - hip) // 8
        side[y, w // 2 - sd : w // 2 + sd] = 255
    pose = {
        "l_shoulder": (w // 2 - 50, sh),
        "r_shoulder": (w // 2 + 50, sh),
        "l_hip": (w // 2 - 40, hip),
        "r_hip": (w // 2 + 40, hip),
    }
    return front, side, pose, sh, hip


def test_waist_is_minimum_in_torso_band():
    front, side, pose, sh, hip = _synthetic_masks()
    from pipeline.measure.markerless import _ProfileView

    side_pv = _ProfileView("side", side, pose, sh, hip + 200, 0.25)
    samples, _ = scan_torso_slices(front, pose, front.shape[1] // 2, 0.25, side_pv, 0.25)
    assert len(samples) > 10
    levels, _ = levels_from_sweep(samples)
    by_name = {lv.name: lv for lv in levels}
    assert by_name["waist"].girth_cm <= by_name["hip"].girth_cm


def test_loose_monotonic_shirt_detected():
    samples = [
        SliceSample(400, 0.40, 30.0, 20.0, 75.0, False),
        SliceSample(450, 0.55, 28.0, 19.0, 72.0, False),
        SliceSample(500, 0.72, 26.0, 18.0, 68.0, False),
        SliceSample(520, 0.80, 24.0, 17.0, 65.0, False),
    ]
    assert detect_loose_top(samples)


def test_fitted_waist_pinch_not_loose_top():
    samples = [
        SliceSample(380, 0.28, 35.0, 22.0, 88.0, False),
        SliceSample(450, 0.48, 30.0, 20.0, 78.0, False),
        SliceSample(480, 0.62, 27.0, 19.0, 72.0, False),
        SliceSample(520, 0.92, 32.0, 20.0, 78.0, False),
    ]
    assert not detect_loose_top(samples)


def test_body_shape_hip_at_least_waist():
    samples = [
        SliceSample(400, 0.28, 32.0, 22.0, 88.0, False),
        SliceSample(450, 0.48, 29.0, 20.0, 80.0, False),
        SliceSample(480, 0.62, 27.0, 19.0, 74.0, False),
        SliceSample(520, 0.92, 26.0, 18.0, 70.0, False),
    ]
    levels, _ = levels_from_body_shape(samples, loose_top=True)
    w = next(l for l in levels if l.name == "waist")
    h = next(l for l in levels if l.name == "hip")
    assert h.girth_cm >= w.girth_cm
