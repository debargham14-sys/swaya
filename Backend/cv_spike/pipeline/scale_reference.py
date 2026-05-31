"""
Scale from a reference object in the photo -> cm-per-pixel, so body measurement
works WITHOUT the subject's height.

Supported references (most robust first):
  - aruco : a printed ArUco marker of known side length (mm)
  - card  : a credit/ID card (ISO 85.6 x 54 mm)
  - a4    : an A4 sheet (210 x 297 mm)

Returns cm_per_px (centimetres per pixel) for that image.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Known real-world reference sizes (mm)
CARD_MM = (85.6, 54.0)   # ISO/IEC 7810 ID-1 (credit card)
A4_MM = (297.0, 210.0)   # long, short


@dataclass
class ScaleResult:
    cm_per_px: float | None
    method: str
    confidence: float
    warning: str | None = None


def _aruco_side_px(img: np.ndarray, dict_name: str = "DICT_4X4_50") -> float | None:
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dict_name))
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = detector.detectMarkers(gray)
    if ids is None or len(corners) == 0:
        return None
    sides = []
    for c in corners:
        p = c[0]
        s = (
            np.linalg.norm(p[0] - p[1])
            + np.linalg.norm(p[1] - p[2])
            + np.linalg.norm(p[2] - p[3])
            + np.linalg.norm(p[3] - p[0])
        ) / 4.0
        sides.append(s)
    return float(np.median(sides))


def scale_from_aruco(img: np.ndarray, marker_mm: float, dict_name: str = "DICT_4X4_50") -> ScaleResult:
    px = _aruco_side_px(img, dict_name)
    if not px or px < 5:
        return ScaleResult(None, "aruco", 0.0, "aruco_not_detected")
    cm_per_px = (marker_mm / 10.0) / px
    return ScaleResult(cm_per_px, "aruco", 0.9)


def _best_rectangle(img: np.ndarray, target_aspect: float, tol: float = 0.18):
    """Find the quadrilateral whose aspect best matches target (long/short)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 7, 50, 50)
    edges = cv2.Canny(gray, 40, 130)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    best, best_score = None, 1e9
    h, w = img.shape[:2]
    for c in contours:
        area = cv2.contourArea(c)
        if area < 0.0008 * h * w:
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        rect = cv2.minAreaRect(c)
        (rw, rh) = rect[1]
        if min(rw, rh) < 8:
            continue
        aspect = max(rw, rh) / min(rw, rh)
        score = abs(aspect - target_aspect)
        if score < best_score and score < tol * target_aspect:
            best, best_score = rect, score
    return best


def scale_from_rectangle(img: np.ndarray, long_mm: float, short_mm: float, method: str) -> ScaleResult:
    target_aspect = long_mm / short_mm
    rect = _best_rectangle(img, target_aspect)
    if rect is None:
        return ScaleResult(None, method, 0.0, f"{method}_not_detected")
    (rw, rh) = rect[1]
    long_px, short_px = max(rw, rh), min(rw, rh)
    # use both dimensions for a robust estimate
    cm_per_px = np.mean([(long_mm / 10.0) / long_px, (short_mm / 10.0) / short_px])
    return ScaleResult(float(cm_per_px), method, 0.6)


def detect_scale(img: np.ndarray, kind: str, marker_mm: float = 50.0) -> ScaleResult:
    kind = kind.lower()
    if kind == "aruco":
        return scale_from_aruco(img, marker_mm)
    if kind == "card":
        return scale_from_rectangle(img, CARD_MM[0], CARD_MM[1], "card")
    if kind == "a4":
        return scale_from_rectangle(img, A4_MM[0], A4_MM[1], "a4")
    return ScaleResult(None, kind, 0.0, "unknown_reference_kind")


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    p = argparse.ArgumentParser(description="ArUco scale reference utilities")
    p.add_argument(
        "--generate",
        type=Path,
        metavar="OUT.png",
        help="Write a printable DICT_4X4_50 marker (default 50 mm when printed at scale)",
    )
    p.add_argument("--marker-mm", type=float, default=50.0, help="Target printed size in mm")
    p.add_argument("--marker-id", type=int, default=0, help="ArUco marker ID")
    p.add_argument("--px", type=int, default=400, help="Marker size in output image pixels")
    args = p.parse_args()

    if args.generate:
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        marker = cv2.aruco.generateImageMarker(dictionary, args.marker_id, args.px)
        pad = 40
        canvas = np.full((args.px + 2 * pad, args.px + 2 * pad), 255, np.uint8)
        canvas[pad : pad + args.px, pad : pad + args.px] = marker
        bgr = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
        args.generate.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(args.generate), bgr)
        print(f"Wrote {args.generate}")
        print(f"Print so the black square measures {args.marker_mm:g} mm x {args.marker_mm:g} mm.")
        print("Hold flat at chest level in front, back, and side photos.")
        raise SystemExit(0)

    # self-test: synthesize an image with a known 50 mm ArUco marker
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    side_px = 120  # pretend 50 mm prints as 120 px
    marker = cv2.aruco.generateImageMarker(dictionary, 0, side_px)
    canvas = np.full((600, 600), 255, np.uint8)
    canvas[100:100 + side_px, 100:100 + side_px] = marker
    bgr = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
    r = scale_from_aruco(bgr, marker_mm=50.0)
    expected = (50.0 / 10.0) / side_px
    print(f"[selftest] cm_per_px got {r.cm_per_px:.5f}, expected {expected:.5f} "
          f"({'OK' if abs(r.cm_per_px - expected) < 1e-3 else 'CHECK'})")
