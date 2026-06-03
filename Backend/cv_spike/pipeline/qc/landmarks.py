"""
Blouse landmark extraction.

Rasterizes the silhouette into a fronto-parallel framework-mm canvas (perspective
removed via the Stage-1 homography), then derives the reference rows and points
the dimensional + symmetry stages need:

  - shoulder line (seam endpoints)
  - bust / underbust / chest rows
  - underarm row (armhole pinch)
  - hem (bottom) and centre-front axis
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from pipeline.qc.charuco import Calibration
from pipeline.qc.framework_spec import STANDARD_A1, FrameworkSpec


def rasterize_to_mm(
    mask_px: np.ndarray,
    calib: Calibration,
    spec: FrameworkSpec = STANDARD_A1,
    mm_scale: float = 1.0,
) -> tuple[np.ndarray, float]:
    """Warp a pixel-space mask into a fronto-parallel mm canvas.

    Returns (mm_mask, mm_scale) where canvas pixel = mm * mm_scale, i.e. 1 px =
    (1 / mm_scale) mm. Perspective distortion is removed by the homography.
    """
    if calib.H_px_to_mm is None:
        raise ValueError("calibration has no homography; cannot rasterize")
    S = np.array([[mm_scale, 0, 0], [0, mm_scale, 0], [0, 0, 1]], dtype=np.float64)
    H = S @ calib.H_px_to_mm
    w = int(round(spec.sheet_w_mm * mm_scale))
    h = int(round(spec.sheet_h_mm * mm_scale))
    warped = cv2.warpPerspective(mask_px, H, (w, h), flags=cv2.INTER_NEAREST)
    return (warped > 127).astype(np.uint8) * 255, mm_scale


def _row_extent(mask: np.ndarray, y: int) -> tuple[int, int, int] | None:
    """Widest horizontal run on row y -> (x_left, x_right, width)."""
    row = mask[int(np.clip(y, 0, mask.shape[0] - 1))]
    on = np.where(row > 0)[0]
    if len(on) == 0:
        return None
    splits = np.where(np.diff(on) > 1)[0]
    groups = np.split(on, splits + 1)
    best = max(groups, key=len)
    return int(best[0]), int(best[-1]), int(best[-1] - best[0])


@dataclass
class Landmarks:
    mm_mask: np.ndarray
    mm_scale: float
    top_y: int
    bottom_y: int
    shoulder_y: int
    shoulder_left: tuple[int, int]
    shoulder_right: tuple[int, int]
    underarm_y: int
    bust_y: int
    underbust_y: int
    chest_y: int
    center_x: float
    width_profile_mm: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def px_to_mm_len(self, px: float) -> float:
        return px / self.mm_scale


def extract_landmarks(
    silhouette_mask_px: np.ndarray,
    calib: Calibration,
    spec: FrameworkSpec = STANDARD_A1,
    mm_scale: float = 1.0,
) -> Landmarks | None:
    mm_mask, mm_scale = rasterize_to_mm(silhouette_mask_px, calib, spec, mm_scale)
    ys = np.where(mm_mask.any(axis=1))[0]
    if len(ys) < 5:
        return None
    top_y, bottom_y = int(ys.min()), int(ys.max())
    height = max(1, bottom_y - top_y)

    # Shoulder line: widest row in the top 12% of the blouse.
    band = range(top_y, top_y + max(2, int(0.12 * height)))
    shoulder_y, shoulder_ext, best_w = top_y, _row_extent(mm_mask, top_y), -1
    for y in band:
        ext = _row_extent(mm_mask, y)
        if ext and ext[2] > best_w:
            best_w, shoulder_y, shoulder_ext = ext[2], y, ext
    if shoulder_ext is None:
        return None
    sl = (shoulder_ext[0], shoulder_y)
    sr = (shoulder_ext[1], shoulder_y)

    bust_y = top_y + int(0.30 * height)
    underbust_y = top_y + int(0.42 * height)
    chest_y = top_y + int(0.18 * height)

    # Underarm: narrowest row between shoulder and bust (armhole pinch).
    underarm_y, min_w = bust_y, 1e9
    for y in range(shoulder_y + 1, bust_y + 1):
        ext = _row_extent(mm_mask, y)
        if ext and ext[2] < min_w:
            min_w, underarm_y = ext[2], y

    center_x = float(np.median(np.where(mm_mask.any(axis=0))[0]))

    def width_at(y: int) -> float:
        ext = _row_extent(mm_mask, y)
        return float(ext[2]) / mm_scale if ext else 0.0

    profile = {
        "shoulder": float(shoulder_ext[2]) / mm_scale,
        "chest": width_at(chest_y),
        "bust": width_at(bust_y),
        "underbust": width_at(underbust_y),
    }
    return Landmarks(
        mm_mask=mm_mask,
        mm_scale=mm_scale,
        top_y=top_y,
        bottom_y=bottom_y,
        shoulder_y=shoulder_y,
        shoulder_left=sl,
        shoulder_right=sr,
        underarm_y=underarm_y,
        bust_y=bust_y,
        underbust_y=underbust_y,
        chest_y=chest_y,
        center_x=center_x,
        width_profile_mm={k: round(v, 1) for k, v in profile.items()},
    )
