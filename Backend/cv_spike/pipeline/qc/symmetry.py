"""
Stage 6 - Symmetry analysis.

Folds the blouse silhouette about its best vertical centre axis (in the
fronto-parallel mm canvas) and measures left/right deviation. Also derives a
couple of named symmetry checks the checklist maps directly: overall silhouette
mirror, shoulder-endpoint symmetry, and hem level.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from pipeline.qc.landmarks import Landmarks, _row_extent
from pipeline.qc.spec import SYMMETRY_TOLERANCE_MM


@dataclass
class SymmetrySubCheck:
    name: str
    deviation_mm: float
    tolerance_mm: float
    status: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "deviation_mm": round(self.deviation_mm, 1),
            "tolerance_mm": self.tolerance_mm,
            "status": self.status,
        }


@dataclass
class SymmetryResult:
    axis_x_mm: float
    max_deviation_mm: float
    mean_deviation_mm: float
    iou: float
    sub_checks: list[SymmetrySubCheck] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "axis_x_mm": round(self.axis_x_mm, 1),
            "max_deviation_mm": round(self.max_deviation_mm, 1),
            "mean_deviation_mm": round(self.mean_deviation_mm, 1),
            "iou": round(self.iou, 3),
            "sub_checks": [c.to_dict() for c in self.sub_checks],
            "warnings": self.warnings,
        }


def _status(dev_mm: float, tol_mm: float) -> str:
    return "pass" if dev_mm <= tol_mm else "fail"


def _best_axis(mm_mask: np.ndarray, top_y: int, bottom_y: int, seed_x: float) -> tuple[float, list[float]]:
    """Search a small window around seed_x for the axis minimising mean |L-R|."""
    best_axis, best_cost, best_devs = seed_x, 1e18, []
    for axis in range(int(seed_x) - 12, int(seed_x) + 13):
        devs: list[float] = []
        for y in range(top_y, bottom_y + 1):
            ext = _row_extent(mm_mask, y)
            if not ext:
                continue
            left = axis - ext[0]
            right = ext[1] - axis
            devs.append(abs(left - right))
        if devs:
            cost = float(np.mean(devs))
            if cost < best_cost:
                best_cost, best_axis, best_devs = cost, float(axis), devs
    return best_axis, best_devs


def analyze_symmetry(lm: Landmarks) -> SymmetryResult:
    mm_mask = lm.mm_mask
    scale = lm.mm_scale
    warnings: list[str] = []

    axis_px, devs_px = _best_axis(mm_mask, lm.top_y, lm.bottom_y, lm.center_x)
    if not devs_px:
        return SymmetryResult(axis_px / scale, 0.0, 0.0, 0.0, [], ["symmetry_no_rows"])

    max_dev_mm = float(np.percentile(devs_px, 95)) / scale  # robust to single-row noise
    mean_dev_mm = float(np.mean(devs_px)) / scale

    # IoU of mask with its mirror about the axis.
    iou = _mirror_iou(mm_mask, axis_px)

    sub: list[SymmetrySubCheck] = []
    tol = SYMMETRY_TOLERANCE_MM
    sub.append(SymmetrySubCheck("silhouette_symmetry", max_dev_mm, tol, _status(max_dev_mm, tol)))

    # Shoulder endpoint symmetry.
    sh_left = axis_px - lm.shoulder_left[0]
    sh_right = lm.shoulder_right[0] - axis_px
    sh_dev_mm = abs(sh_left - sh_right) / scale
    sub.append(SymmetrySubCheck("shoulder_seam_symmetry", sh_dev_mm, tol, _status(sh_dev_mm, tol)))

    # Hem level: bottom-most fg row on left vs right half.
    hem_dev_mm = _hem_level_dev(mm_mask, axis_px, lm.top_y, lm.bottom_y) / scale
    hem_tol = 3.0
    sub.append(SymmetrySubCheck("hem_level", hem_dev_mm, hem_tol, _status(hem_dev_mm, hem_tol)))

    return SymmetryResult(
        axis_x_mm=axis_px / scale,
        max_deviation_mm=max_dev_mm,
        mean_deviation_mm=mean_dev_mm,
        iou=iou,
        sub_checks=sub,
        warnings=warnings,
    )


def _mirror_iou(mm_mask: np.ndarray, axis_px: float) -> float:
    h, w = mm_mask.shape[:2]
    xs = (np.arange(w) - axis_px).astype(np.float64)
    src_x = np.round(axis_px - xs).astype(int)  # mirrored column index
    valid = (src_x >= 0) & (src_x < w)
    mirror = np.zeros_like(mm_mask)
    mirror[:, valid] = mm_mask[:, src_x[valid]]
    a = mm_mask > 0
    b = mirror > 0
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter / union) if union else 0.0


def _hem_level_dev(mm_mask: np.ndarray, axis_px: float, top_y: int, bottom_y: int) -> float:
    ax = int(round(axis_px))
    left = mm_mask[:, max(0, ax - 80):ax]
    right = mm_mask[:, ax:min(mm_mask.shape[1], ax + 80)]

    def bottom_row(block: np.ndarray) -> int | None:
        ys = np.where(block.any(axis=1))[0]
        return int(ys.max()) if len(ys) else None

    bl, br = bottom_row(left), bottom_row(right)
    if bl is None or br is None:
        return 0.0
    return abs(bl - br)
