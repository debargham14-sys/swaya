"""
Stage 2 - QC framework inner-boundary detection.

The inner edge of the framework (the hollow centre of the picture frame) is a
known constant in framework-mm coordinates. Once Stage 1 gives us the px <-> mm
homography, we simply project that known rectangle back into the photo to get
the in-image "measurement zone": the region within which the blouse should fit.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from pipeline.qc.charuco import Calibration
from pipeline.qc.framework_spec import STANDARD_A1, FrameworkSpec


@dataclass
class MeasurementZone:
    """Inner framework rectangle, in both mm and px."""

    corners_mm: np.ndarray  # 4x2, clockwise from top-left
    corners_px: np.ndarray  # 4x2, clockwise from top-left
    mask_px: np.ndarray     # uint8 zone mask in the photo's pixel space

    def contains_px(self, x: float, y: float) -> bool:
        return bool(cv2.pointPolygonTest(self.corners_px.astype(np.float32), (float(x), float(y)), False) >= 0)

    def to_dict(self) -> dict:
        return {
            "corners_mm": self.corners_mm.round(1).tolist(),
            "corners_px": self.corners_px.round(1).tolist(),
        }


def detect_measurement_zone(
    img_shape: tuple[int, int],
    calib: Calibration,
    spec: FrameworkSpec = STANDARD_A1,
) -> MeasurementZone:
    """Project the known inner-edge rectangle into the photo via the homography."""
    if calib.H_mm_to_px is None:
        raise ValueError("calibration has no homography; cannot locate zone")

    corners_mm = np.array(spec.zone_corners_mm, dtype=np.float64)
    corners_px = calib.mm_to_px(corners_mm)

    h, w = img_shape[:2]
    mask = np.zeros((h, w), np.uint8)
    poly = corners_px.round().astype(np.int32)
    cv2.fillPoly(mask, [poly], 255)

    return MeasurementZone(corners_mm=corners_mm, corners_px=corners_px, mask_px=mask)


def corners_visible(calib: Calibration, img_shape: tuple[int, int], spec: FrameworkSpec = STANDARD_A1) -> bool:
    """True if all four fiducial centres project inside the frame (blouse not covering corners)."""
    if calib.H_mm_to_px is None:
        return False
    h, w = img_shape[:2]
    centers_mm = np.array([spec.fiducial_centers_mm[i] for i in spec.fiducial_ids()], dtype=np.float64)
    centers_px = calib.mm_to_px(centers_mm)
    return bool(np.all((centers_px[:, 0] >= 0) & (centers_px[:, 0] < w) &
                       (centers_px[:, 1] >= 0) & (centers_px[:, 1] < h)))
