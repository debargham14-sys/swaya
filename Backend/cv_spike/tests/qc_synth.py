"""Synthetic QC-framework + blouse image helpers for tests."""

from __future__ import annotations

import cv2
import numpy as np

from pipeline.qc import charuco
from pipeline.qc.framework_spec import STANDARD_A1 as S

MARGIN_PX = 20


def make_framework_image(px_per_mm: float = 2.0) -> tuple[np.ndarray, float]:
    return charuco.synthesize_framework_image(S, px_per_mm=px_per_mm, margin_px=MARGIN_PX)


def make_qc_image(px_per_mm: float = 2.0) -> tuple[np.ndarray, float]:
    """Cream framework with a magenta blouse drawn inside the measurement zone."""
    img, ppm = make_framework_image(px_per_mm)

    def mm2px(x_mm: float, y_mm: float) -> tuple[int, int]:
        return (int(round(x_mm * ppm)) + MARGIN_PX, int(round(y_mm * ppm)) + MARGIN_PX)

    cx = S.sheet_w_mm / 2
    top, bottom = 90.0, 690.0
    pts_mm = [
        (cx - 190, top), (cx - 150, top + 40), (cx - 215, top + 180), (cx - 205, bottom),
        (cx + 205, bottom), (cx + 215, top + 180), (cx + 150, top + 40), (cx + 190, top),
    ]
    poly = np.array([mm2px(x, y) for x, y in pts_mm], np.int32)
    cv2.fillPoly(img, [poly], (150, 40, 150))
    return img, ppm


def make_qc_jpeg_bytes(px_per_mm: float = 2.0) -> bytes:
    img, _ = make_qc_image(px_per_mm)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    assert ok
    return buf.tobytes()
