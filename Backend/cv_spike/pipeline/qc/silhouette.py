"""
Stage 3 - Blouse silhouette extraction.

Within the measurement zone, separate the blouse from the framework's cream
background using Lab colour distance (the background is sampled from the zone
border, where the blouse should not reach) refined with GrabCut, then cleaned
with the shared morphology helper from the body-measurement pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from pipeline.common.mask_ops import clean_mask
from pipeline.qc.framework import MeasurementZone


@dataclass
class Silhouette:
    mask: np.ndarray            # uint8 0/255 blouse mask in photo px space
    contour: np.ndarray | None  # Nx2 largest external contour, or None
    area_px: int
    fill_ratio: float           # blouse area / zone area
    warnings: list[str]


def _zone_border_bg_lab(lab: np.ndarray, zone_mask: np.ndarray) -> np.ndarray:
    """Sample background colour (mean Lab) from a thin ring inside the zone edge."""
    eroded = cv2.erode(zone_mask, np.ones((25, 25), np.uint8))
    ring = cv2.subtract(zone_mask, eroded)
    pts = lab[ring > 0]
    if len(pts) < 50:
        pts = lab[zone_mask > 0]
    return pts.reshape(-1, 3).mean(axis=0)


def extract_silhouette(
    img_bgr: np.ndarray,
    zone: MeasurementZone,
    color_dist_thresh: float = 28.0,
    use_grabcut: bool = True,
) -> Silhouette:
    warnings: list[str] = []
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    zone_mask = zone.mask_px

    bg_lab = _zone_border_bg_lab(lab, zone_mask)
    dist = np.linalg.norm(lab - bg_lab[None, None, :], axis=2)
    fg = ((dist > color_dist_thresh) & (zone_mask > 0)).astype(np.uint8) * 255

    if use_grabcut and fg.sum() > 0:
        fg = _grabcut_refine(img_bgr, fg, zone_mask, warnings)

    fg = cv2.bitwise_and(fg, fg, mask=zone_mask)
    if fg.sum() == 0:
        warnings.append("no_blouse_detected_in_zone")
        return Silhouette(mask=fg, contour=None, area_px=0, fill_ratio=0.0, warnings=warnings)

    clean = clean_mask(fg)
    clean = cv2.bitwise_and(clean, clean, mask=zone_mask)

    cnts, _ = cv2.findContours(clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contour = max(cnts, key=cv2.contourArea).reshape(-1, 2) if cnts else None
    area = int((clean > 0).sum())
    zone_area = int((zone_mask > 0).sum()) or 1
    fill = area / zone_area
    if fill < 0.04:
        warnings.append("blouse_fill_ratio_low")
    if fill > 0.96:
        warnings.append("blouse_overflows_zone_check_framing")
    return Silhouette(mask=clean, contour=contour, area_px=area, fill_ratio=round(fill, 3), warnings=warnings)


def _grabcut_refine(
    img_bgr: np.ndarray, fg_seed: np.ndarray, zone_mask: np.ndarray, warnings: list[str]
) -> np.ndarray:
    gc = np.full(img_bgr.shape[:2], cv2.GC_BGD, np.uint8)
    gc[zone_mask > 0] = cv2.GC_PR_BGD
    # confident foreground = eroded seed; probable foreground = dilated seed
    sure_fg = cv2.erode(fg_seed, np.ones((7, 7), np.uint8))
    prob_fg = cv2.dilate(fg_seed, np.ones((9, 9), np.uint8))
    gc[prob_fg > 0] = cv2.GC_PR_FGD
    gc[sure_fg > 0] = cv2.GC_FGD
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(img_bgr, gc, None, bgd, fgd, 3, cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        warnings.append("grabcut_failed_used_color_threshold")
        return fg_seed
    out = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    if out.sum() < 0.2 * fg_seed.sum():
        warnings.append("grabcut_underfilled_used_color_threshold")
        return fg_seed
    return out
