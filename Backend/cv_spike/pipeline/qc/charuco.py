"""
Stage 1 - ChArUco / ArUco detection and calibration.

Finds the four corner fiducials on the QC framework, then builds a homography
that maps image pixels to framework millimetres (and back). This is the ground
truth used by every later stage to measure the blouse in real units and to
correct for perspective distortion.

  - 4 corners found -> full perspective homography (cv2.findHomography)
  - 3 corners found -> affine fallback (cv2.getAffineTransform)
  - < 3 corners      -> needs_retake = True
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from pipeline.qc.framework_spec import STANDARD_A1, FrameworkSpec

MIN_CORNERS = 3


@dataclass
class Calibration:
    """px <-> mm mapping for one QC photo."""

    H_px_to_mm: np.ndarray | None
    H_mm_to_px: np.ndarray | None
    corners_found: int
    detected_ids: list[int]
    mm_per_px: float | None
    method: str
    needs_retake: bool
    warnings: list[str] = field(default_factory=list)

    def px_to_mm(self, pts_px: np.ndarray) -> np.ndarray:
        """Map Nx2 pixel points to Nx2 framework-mm points."""
        return _apply_h(self.H_px_to_mm, pts_px)

    def mm_to_px(self, pts_mm: np.ndarray) -> np.ndarray:
        """Map Nx2 framework-mm points to Nx2 pixel points."""
        return _apply_h(self.H_mm_to_px, pts_mm)

    def to_dict(self) -> dict:
        return {
            "corners_found": self.corners_found,
            "detected_ids": self.detected_ids,
            "mm_per_px": round(self.mm_per_px, 4) if self.mm_per_px else None,
            "method": self.method,
            "needs_retake": self.needs_retake,
            "warnings": self.warnings,
        }


def _apply_h(H: np.ndarray | None, pts: np.ndarray) -> np.ndarray:
    if H is None:
        raise ValueError("no homography available (calibration failed)")
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 1, 2)
    out = cv2.perspectiveTransform(pts, H)
    return out.reshape(-1, 2)


def detect_fiducials(
    img_bgr: np.ndarray, dict_name: str = "DICT_4X4_50"
) -> dict[int, np.ndarray]:
    """Detect framework fiducials; return {marker_id: centre_px (x, y)}."""
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dict_name))
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = detector.detectMarkers(gray)
    centers: dict[int, np.ndarray] = {}
    if ids is None:
        return centers
    for c, i in zip(corners, ids.flatten()):
        centers[int(i)] = c[0].mean(axis=0).astype(np.float64)
    return centers


def _homography_from_matches(
    src_px: np.ndarray, dst_mm: np.ndarray
) -> tuple[np.ndarray | None, str]:
    n = len(src_px)
    if n >= 4:
        H, _ = cv2.findHomography(src_px, dst_mm, method=0)
        return H, "homography"
    if n == 3:
        M = cv2.getAffineTransform(
            src_px[:3].astype(np.float32), dst_mm[:3].astype(np.float32)
        )
        H = np.vstack([M, [0.0, 0.0, 1.0]])
        return H, "affine"
    return None, "insufficient"


def _estimate_mm_per_px(centers_px: dict[int, np.ndarray], spec: FrameworkSpec) -> float | None:
    """Median real distance / pixel distance over all detected fiducial pairs."""
    ids = sorted(centers_px.keys())
    ratios: list[float] = []
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            ia, ib = ids[a], ids[b]
            if ia not in spec.fiducial_centers_mm or ib not in spec.fiducial_centers_mm:
                continue
            d_px = float(np.linalg.norm(centers_px[ia] - centers_px[ib]))
            mm_a = np.array(spec.fiducial_centers_mm[ia])
            mm_b = np.array(spec.fiducial_centers_mm[ib])
            d_mm = float(np.linalg.norm(mm_a - mm_b))
            if d_px > 1.0:
                ratios.append(d_mm / d_px)
    return float(np.median(ratios)) if ratios else None


def calibrate(img_bgr: np.ndarray, spec: FrameworkSpec = STANDARD_A1) -> Calibration:
    """Detect fiducials and build the px <-> mm calibration for this photo."""
    warnings: list[str] = []
    centers = detect_fiducials(img_bgr, spec.fiducial_dict)
    known = {i: centers[i] for i in centers if i in spec.fiducial_centers_mm}
    found = len(known)

    if found < MIN_CORNERS:
        warnings.append(f"only_{found}_of_4_fiducials_detected")
        return Calibration(
            H_px_to_mm=None,
            H_mm_to_px=None,
            corners_found=found,
            detected_ids=sorted(known.keys()),
            mm_per_px=None,
            method="none",
            needs_retake=True,
            warnings=warnings,
        )

    ids = sorted(known.keys())
    src_px = np.array([known[i] for i in ids], dtype=np.float64)
    dst_mm = np.array([spec.fiducial_centers_mm[i] for i in ids], dtype=np.float64)

    H, method = _homography_from_matches(src_px, dst_mm)
    if H is None:
        warnings.append("homography_fit_failed")
        return Calibration(
            None, None, found, ids, None, "none", True, warnings
        )
    H_inv = np.linalg.inv(H)

    if found == 3:
        warnings.append("3_corner_affine_no_perspective_correction")

    mm_per_px = _estimate_mm_per_px(known, spec)
    return Calibration(
        H_px_to_mm=H,
        H_mm_to_px=H_inv,
        corners_found=found,
        detected_ids=ids,
        mm_per_px=mm_per_px,
        method=method,
        needs_retake=False,
        warnings=warnings,
    )


# --------------------------------------------------------------------------
# Test / tooling helper: synthesize a framework photo with markers in place.
# --------------------------------------------------------------------------
def synthesize_framework_image(
    spec: FrameworkSpec = STANDARD_A1,
    px_per_mm: float = 2.0,
    bg_value: int = 232,
    margin_px: int = 20,
) -> tuple[np.ndarray, float]:
    """Render a blank cream framework with the four corner ArUco markers.

    Returns (image_bgr, px_per_mm). Pixel = mm * px_per_mm + margin_px, so the
    expected px<->mm mapping is exactly known for tests.
    """
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, spec.fiducial_dict))
    w = int(spec.sheet_w_mm * px_per_mm) + 2 * margin_px
    h = int(spec.sheet_h_mm * px_per_mm) + 2 * margin_px
    canvas = np.full((h, w, 3), bg_value, np.uint8)

    side_px = max(8, int(round(spec.fiducial_mm * px_per_mm)))
    for mid, (cx_mm, cy_mm) in spec.fiducial_centers_mm.items():
        marker = cv2.aruco.generateImageMarker(dictionary, mid, side_px)
        marker_bgr = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
        cx = int(round(cx_mm * px_per_mm)) + margin_px
        cy = int(round(cy_mm * px_per_mm)) + margin_px
        x0, y0 = cx - side_px // 2, cy - side_px // 2
        x1, y1 = x0 + side_px, y0 + side_px
        if 0 <= x0 and 0 <= y0 and x1 <= w and y1 <= h:
            canvas[y0:y1, x0:x1] = marker_bgr
    return canvas, px_per_mm
