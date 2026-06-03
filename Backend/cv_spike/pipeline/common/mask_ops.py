"""Binary-mask morphology helpers shared across engines."""

from __future__ import annotations

import cv2
import numpy as np


def clean_mask(m: np.ndarray) -> np.ndarray:
    """Open/close, keep the largest connected component, and fill its contour."""
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8), 2)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if num > 1:
        best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        m = np.where(labels == best, 255, 0).astype(np.uint8)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(m)
    cv2.drawContours(filled, cnts, -1, 255, -1)
    return filled
