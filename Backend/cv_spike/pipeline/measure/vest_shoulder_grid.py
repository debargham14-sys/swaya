"""
Grid-cell shoulder thread — ported from Swaya-Studio/ImageToMeasurements (``1cm``
branch: ``vest_measure/grid.py`` + ``shoulder.py::thread_length``).

The DSV vest's printed grid is plain 1-inch (2.54 cm) squares of inextensible
spunbond, so the spacing between two grid lines is one inch of *body-surface arc
length* no matter how foreshortened it looks where the body curves away. We
therefore measure shoulder-to-shoulder as a SURFACE arc — count 1-inch grid cells
between the two shoulder points for the horizontal span ``du``, add the vertical
shoulder slope ``dv``, and combine ``thread = hypot(du, dv)`` — instead of a flat
``px/cm * straight pixel distance`` (which under-reads across the rounded back).

Scale (px/cm) is read locally from the nearby ChArUco shoulder patches; the patches
give SCALE only and are never the shoulder endpoints. On the back the endpoints are
the outermost vest-silhouette points near the shoulder row (the red neck->shoulder
tape that anchors the front acromion is absent on the back, matching the upstream
silhouette fallback).

Self-contained: OpenCV + NumPy only, so it ships in the slim deploy image.
"""

from __future__ import annotations

import cv2
import numpy as np

# One printed grid square == 1 inch. (Upstream config.GRID_CM on the 1cm branch.)
GRID_CM = 2.54


# --- grid-line detection (ported from grid.py) --------------------------------
def _line_response(gray: np.ndarray) -> np.ndarray:
    """Bright where there is a thin DARK vertical line (d^2/dx^2 of the image)."""
    g = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), 1.5)
    d2 = cv2.Sobel(g, cv2.CV_32F, 2, 0, ksize=5)
    return np.clip(d2, 0, None)


def _peaks(sig: np.ndarray, min_sep: int, rel: float = 0.28) -> list[int]:
    base = cv2.GaussianBlur(sig.reshape(-1, 1), (0, 0), max(2, min_sep)).ravel()
    s = sig - base
    thr = rel * s.max() if s.max() > 0 else np.inf
    out: list[int] = []
    for i in range(1, len(s) - 1):
        if s[i] > thr and s[i] >= s[i - 1] and s[i] >= s[i + 1]:
            if not out or i - out[-1] >= min_sep:
                out.append(i)
            elif s[i] > s[out[-1]]:
                out[-1] = i
    return out


def vertical_lines_at(
    img: np.ndarray, y: int, vest_mask: np.ndarray, ppc: float, band: int = 44
) -> list[int]:
    """x-positions of the 1-inch vertical grid lines crossing row ``y``, on the vest."""
    h, w = img.shape[:2]
    y = int(np.clip(y, 0, h - 1))
    y0, y1 = max(0, y - band // 2), min(h, y + band // 2)
    gray = cv2.cvtColor(img[y0:y1], cv2.COLOR_BGR2GRAY)
    sat = cv2.cvtColor(img[y0:y1], cv2.COLOR_BGR2HSV)[..., 1]
    resp = _line_response(gray) * (sat < 70) * (vest_mask[y0:y1] > 0)
    prof = resp.sum(0)
    xs = _peaks(prof, min_sep=max(1, int(0.55 * ppc * GRID_CM)))
    return [x for x in xs if vest_mask[y, x] > 0]


def arc_cm(x_left: float, x_right: float, line_xs: list[int], ppc: float) -> dict:
    """Surface arc-length (cm) from ``x_left`` to ``x_right`` along a row, fusing the
    grid with the ChArUco scale. Counts 1-inch cells between detected lines (each gap
    rounded to a whole number of cells via the patch scale, so a missed line becomes
    two cells rather than corrupting the result) plus sub-cell end remainders. Falls
    back to flat px->cm when fewer than two grid lines lie between the points."""
    straight_cm = abs(x_right - x_left) / ppc
    lo, hi = min(x_left, x_right), max(x_left, x_right)
    xs = sorted(x for x in line_xs if lo - 2 < x < hi + 2)
    if len(xs) < 2:
        return {"grid_cm": straight_cm, "straight_cm": straight_cm, "n_cells": 0, "used": "scale"}
    total = abs(xs[0] - lo) / ppc  # leading partial
    n_cells = 0
    for a, b in zip(xs[:-1], xs[1:]):
        cells = max(1, round((b - a) / (ppc * GRID_CM)))
        total += cells * GRID_CM
        n_cells += cells
    total += abs(hi - xs[-1]) / ppc  # trailing partial
    return {"grid_cm": total, "straight_cm": straight_cm, "n_cells": n_cells, "used": "grid"}


# --- vest silhouette (ported from ImageToMeasurements body._vest_mask) ---------
def _person_mask(img_bgr: np.ndarray) -> np.ndarray | None:
    """MediaPipe person segmentation via the shared markerless worker (handles the
    macOS GL subprocess). Best-effort: returns None if pose can't run."""
    try:
        from pipeline.measure.markerless import _run_pose_landmarker

        _, mask = _run_pose_landmarker(img_bgr)
    except Exception:  # noqa: BLE001
        return None
    if mask is None or isinstance(mask, str):
        return None
    return (mask > 0).astype(np.uint8)


def build_vest_mask(
    img_bgr: np.ndarray, person: np.ndarray, patch_centers: list
) -> np.ndarray:
    """White spunbond inside the person: bright + low saturation, bridged across the
    coloured guide lines / dark patches, keeping the component(s) the patches sit in.

    This excludes bare arms / coloured sleeves (high saturation), so the shoulder tips
    land on the vest edge rather than a flailed elbow — the over-wide-mask failure the
    old grid-texture ``segment_garment`` hits on the light apron vest.
    """
    h, w = person.shape
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    bright = ((hsv[..., 2] > 110) & (hsv[..., 1] < 70) & (person > 0)).astype(np.uint8)
    m = cv2.morphologyEx(bright, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 81)))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((45, 45), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m)
    if n <= 1:
        return m
    keep: set[int] = set()
    for cx, cy in (patch_centers or []):
        cx, cy = int(np.clip(cx, 0, w - 1)), int(np.clip(cy, 0, h - 1))
        win = lab[max(0, cy - 50):cy + 50, max(0, cx - 50):cx + 50]
        vals = win[win > 0]
        if len(vals):
            keep.add(int(np.bincount(vals).argmax()))
    if not keep:
        keep = {1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))}
    return np.isin(lab, list(keep)).astype(np.uint8)


# --- shoulder thread ----------------------------------------------------------
def shoulder_tips(
    vest_mask: np.ndarray, shoulder_y: int, band: int
) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """Leftmost & rightmost vest-silhouette points around the shoulder row.
    The vest mask excludes the arms, so these stand in for the shoulder tips
    (upstream ``shoulder.auto_shoulder_tips``)."""
    h = vest_mask.shape[0]
    y0, y1 = max(0, shoulder_y - band), min(h, shoulder_y + band)
    ys, xs = np.where(vest_mask[y0:y1] > 0)
    if len(xs) == 0:
        return None
    iL, iR = int(xs.argmin()), int(xs.argmax())
    pL = (int(xs[iL]), int(ys[iL] + y0))
    pR = (int(xs[iR]), int(ys[iR] + y0))
    return pL, pR


def thread_cm(
    img: np.ndarray,
    pL: tuple[int, int],
    pR: tuple[int, int],
    vest_mask: np.ndarray,
    ppc: float,
) -> dict:
    """Shoulder thread (surface) length cm between two shoulder points.

    ``du`` = horizontal surface span via the grid; ``dv`` = vertical drop between the
    points (shoulder slope) via the flat scale; ``thread = hypot(du, dv)``."""
    y_mid = int((pL[1] + pR[1]) / 2)
    lines = vertical_lines_at(img, y_mid, vest_mask, ppc)
    r = arc_cm(pL[0], pR[0], lines, ppc)
    du = r["grid_cm"]
    dv = abs(pL[1] - pR[1]) / ppc
    thread = float(np.hypot(du, dv))
    return {
        "thread_cm": thread,
        "du_cm": du,
        "dv_cm": dv,
        "straight_cm": float(np.hypot(pR[0] - pL[0], pR[1] - pL[1]) / ppc),
        "n_cells": r["n_cells"],
        "n_lines": len(lines),
        "used": r["used"],
        "pL": pL,
        "pR": pR,
    }


def measure_back_shoulder(
    img_bgr: np.ndarray,
    det: dict[str, dict],
    *,
    vest_mask: np.ndarray | None = None,
    person_mask: np.ndarray | None = None,
    left: str = "BSH_L",
    right: str = "BSH_R",
) -> dict | None:
    """End-to-end back shoulder-to-shoulder via the 1-inch grid.

    Endpoints: outermost vest-silhouette points around the back-shoulder patch row.
    Scale: local px/cm from the ``BSH_L``/``BSH_R`` patches (px_per_mm * 10).

    The vest silhouette is the MediaPipe person mask narrowed to the white spunbond
    (``build_vest_mask``); pass ``vest_mask`` directly to skip that (used in tests), or
    ``person_mask`` to skip only the pose call. Returns the ``thread_cm`` dict (+ ``ppc``)
    or None if scale or silhouette is unavailable.
    """
    scales_mm = [det[m]["px_per_mm"] for m in (left, right) if m in det]
    if not scales_mm:
        scales_mm = [d["px_per_mm"] for d in det.values()]
    if not scales_mm:
        return None
    ppc = float(np.mean(scales_mm)) * 10.0
    if ppc <= 0:
        return None

    if vest_mask is None:
        if person_mask is None:
            person_mask = _person_mask(img_bgr)
        if person_mask is None:
            return None
        vest_mask = build_vest_mask(
            img_bgr, (person_mask > 0).astype(np.uint8), [d["center"] for d in det.values()]
        )

    centers = [det[m]["center"] for m in (left, right) if m in det]
    if centers:
        shoulder_y = int(np.mean([c[1] for c in centers]))
    else:
        shoulder_y = int(img_bgr.shape[0] * 0.22)
    band = max(40, int(1.5 * GRID_CM * ppc))  # ~1.5 inch around the shoulder row
    tips = shoulder_tips(vest_mask, shoulder_y, band)
    if tips is None:
        return None
    out = thread_cm(img_bgr, tips[0], tips[1], vest_mask, ppc)
    out["ppc"] = ppc
    return out
