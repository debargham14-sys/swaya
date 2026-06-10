"""
DSV ChArUco vest measurement (BETA) — front bust/waist/hip girths for tailoring.

The worn vest carries 14 uniquely-identifiable 5x4 ChArUco boards (one shared
DICT_4X4_250, non-overlapping 10-id blocks, so ``id // 10`` = landmark index)
plus a woven 1 cm grid. Each board is a known-size scale reference.

Algorithm (validated on a size-12 form, front view, to ~1.5% after calibration):
  1. detect markers -> per-landmark center + local px/mm (inner marker = 9 mm)
  2. segment the garment from grid-texture energy, keep the marker blob
  3. snap each band to its anthropometric extremum near the marker anchor
     (bust = widest, waist = narrowest, hip = widest, bounded window)
  4. front edge-to-edge width -> circular girth x VEST_CALIBRATION_FACTOR

Scope/limits: front view only is trusted; side depth (true ellipse girth) and
height are not reliable from current captures. The calibration factor is fit to
ONE form — collect tailor ground truth and re-fit before trusting absolutely.
This module is deliberately self-contained (deploy image ships only api/ +
pipeline/, not notebooks/).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np

# --- vest marker scheme (mirrors notebooks/charuco_dsv_lib.py registry) -------
VEST_DICT = "DICT_4X4_250"
MARKER_MM = 9.0
IDS_PER_BOARD = 10
VEST_MARKER_NAMES = (
    "FSH_L", "FSH_R", "FB", "FW", "FH", "SR_U", "SR_L",
    "SL_U", "SL_L", "BSH_L", "BSH_R", "UB", "MB", "LB",
)
MM_PER_IN = 25.4

# Calibration: front circular girth reads ~4% low vs tape ground truth on the
# size-12 form (bust -2.7%, waist -3.5%, hip -5.3% before correction). One global
# factor lands all three within ~1.5%. FIT TO ONE FORM — revisit with more data.
VEST_CALIBRATION_FACTOR = 1.04

# Anthropometric band refinement: snap from the marker anchor to the true
# extremum within a bounded window (mm; + = below the marker). Robust to where
# the marker was actually taped.
_BAND_REFINE = {
    "bust": {"dy_lo_mm": -35, "dy_hi_mm": 35, "mode": "max"},
    "waist": {"dy_lo_mm": -35, "dy_hi_mm": 35, "mode": "min"},
    "hip": {"dy_lo_mm": -20, "dy_hi_mm": 75, "mode": "max"},
}
_FRONT_BAND_MARKER = {"FB": "bust", "FW": "waist", "FH": "hip"}
_BACK_MARKERS = ("BSH_L", "BSH_R", "UB", "MB", "LB")


@dataclass
class VestMeasurement:
    backend: str = "vest_charuco"
    calibration_factor: float = VEST_CALIBRATION_FACTOR
    views: list[str] = field(default_factory=list)
    markers_found: list[str] = field(default_factory=list)
    scale_px_per_mm: float | None = None
    # name -> {"cm", "in", "kind": girth|width|length}
    measurements: dict[str, dict] = field(default_factory=dict)
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def add(self, name: str, cm: float, kind: str) -> None:
        cm = float(cm)  # coerce numpy floats -> JSON-serializable Python float
        self.measurements[name] = {"cm": round(cm, 1), "in": round(cm / 2.54, 1), "kind": kind}

    def to_dict(self) -> dict:
        d = asdict(self)
        # Flat girth maps kept for backward compatibility with existing clients.
        girth = {k: v for k, v in self.measurements.items() if v["kind"] == "girth"}
        d["girths_cm"] = {k: v["cm"] for k, v in girth.items()}
        d["girths_in"] = {k: v["in"] for k, v in girth.items()}
        d["measurements_reliable"] = bool(girth) and self.confidence >= 0.5
        return d


# --- detection ----------------------------------------------------------------
def _detector_params() -> cv2.aruco.DetectorParameters:
    """Tuned for small / slightly curved markers on worn fabric (better recall)."""
    p = cv2.aruco.DetectorParameters()
    p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    p.adaptiveThreshWinSizeMin = 3
    p.adaptiveThreshWinSizeMax = 53
    p.adaptiveThreshWinSizeStep = 8
    p.minMarkerPerimeterRate = 0.02   # accept smaller markers
    p.polygonalApproxAccuracyRate = 0.06
    return p


def detect_markers(gray: np.ndarray) -> dict[str, dict]:
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, VEST_DICT))
    detector = cv2.aruco.ArucoDetector(dictionary, _detector_params())
    corners, ids, _ = detector.detectMarkers(gray)
    acc: dict[int, dict] = {}
    if ids is None:
        return {}
    for m, i in zip(corners, ids.flatten()):
        b = int(i) // IDS_PER_BOARD
        if b >= len(VEST_MARKER_NAMES):
            continue
        side = float(np.mean([np.linalg.norm(m[0][k] - m[0][(k + 1) % 4]) for k in range(4)]))
        acc.setdefault(b, {"sides": [], "ctrs": []})
        acc[b]["sides"].append(side)
        acc[b]["ctrs"].append(m[0].mean(axis=0))
    return {
        VEST_MARKER_NAMES[b]: {
            "center": np.mean(v["ctrs"], axis=0),
            "px_per_mm": float(np.median(v["sides"]) / MARKER_MM),
            "n": len(v["sides"]),
        }
        for b, v in acc.items()
    }


# --- silhouette ---------------------------------------------------------------
def _fill_holes(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    ff = mask.copy()
    z = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(ff, z, (0, 0), 1)
    return (mask | (1 - ff)).astype(np.uint8)


def segment_garment(img: np.ndarray, centers: list[np.ndarray]) -> np.ndarray:
    """Garment mask from grid-texture energy, keeping the marker-centroid blob."""
    h, w = img.shape[:2]
    work = 1400
    s = work / max(h, w)
    small = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gx = cv2.Scharr(gray, cv2.CV_32F, 1, 0)
    gy = cv2.Scharr(gray, cv2.CV_32F, 0, 1)
    energy = cv2.boxFilter(cv2.magnitude(gx, gy), -1, (51, 51))
    energy /= energy.max() + 1e-6
    m = (energy > np.percentile(energy, 62)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    cen = np.clip((np.mean(centers, axis=0) * s).astype(int),
                  [0, 0], [small.shape[1] - 1, small.shape[0] - 1])
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    lid = int(lab[cen[1], cen[0]])
    if lid == 0 and n > 1:
        lid = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    m = (lab == lid).astype(np.uint8) if lid else m
    m = _fill_holes(m)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8))
    return cv2.resize(m, (w, h), interpolation=cv2.INTER_NEAREST)


def _band_extent(mask: np.ndarray, y: int, cx: int, half: int = 18) -> tuple[int, int] | None:
    h, w = mask.shape
    y = int(np.clip(y, half, h - half - 1))
    row = (mask[y - half:y + half].sum(axis=0) > half).astype(np.uint8)
    xs = np.where(row)[0]
    if len(xs) < 10:
        return None
    groups = np.split(xs, np.where(np.diff(xs) > 8)[0] + 1)
    cx = int(np.clip(cx, 0, w - 1))
    best = min(groups, key=lambda g: 0 if g[0] <= cx <= g[-1] else min(abs(g[0] - cx), abs(g[-1] - cx)))
    return int(best[0]), int(best[-1])


def _refine_band(mask, y0, cx, px_per_mm, dy_lo_mm, dy_hi_mm, mode) -> tuple[int, int, int] | None:
    lo = int(y0 + dy_lo_mm * px_per_mm)
    hi = int(y0 + dy_hi_mm * px_per_mm)
    rows, widths = [], []
    for y in range(min(lo, hi), max(lo, hi) + 1, 6):
        ext = _band_extent(mask, y, cx)
        if ext:
            rows.append((y, ext[0], ext[1]))
            widths.append(ext[1] - ext[0])
    if not rows:
        return None
    target = np.percentile(widths, 90 if mode == "max" else 10)
    return rows[int(np.argmin(np.abs(np.array(widths) - target)))]


# --- girth --------------------------------------------------------------------
def circular_girth_cm(width_cm: float, factor: float = VEST_CALIBRATION_FACTOR) -> float:
    return math.pi * width_cm * factor


def ellipse_girth_cm(width_cm: float, depth_cm: float, factor: float = VEST_CALIBRATION_FACTOR) -> float:
    a, b = width_cm / 2.0, depth_cm / 2.0
    h = ((a - b) / (a + b)) ** 2 if (a + b) else 0.0
    return float(math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))) * factor


_FRONT_ANY = ("FSH_L", "FSH_R", "FB", "FW", "FH")


def _span_width_cm(mask, det, left, right, factor_unused=None) -> float | None:
    """Silhouette width (cm) at the mid-level of two markers — robust to marker x."""
    cl, cr = det[left]["center"], det[right]["center"]
    y = int((cl[1] + cr[1]) / 2)
    cx = int((cl[0] + cr[0]) / 2)
    scale = (det[left]["px_per_mm"] + det[right]["px_per_mm"]) / 2.0
    ext = _band_extent(mask, y, cx)
    if not ext or scale <= 0:
        return None
    return (ext[1] - ext[0]) / scale / 10.0


def _vertical_length_cm(det, top_markers, bottom) -> float | None:
    """Vertical body length (cm) between a top landmark and a bottom marker."""
    tops = [det[m] for m in top_markers if m in det]
    if not tops or bottom not in det:
        return None
    ty = sum(t["center"][1] for t in tops) / len(tops)
    by = det[bottom]["center"][1]
    scale = (sum(t["px_per_mm"] for t in tops) / len(tops) + det[bottom]["px_per_mm"]) / 2.0
    if scale <= 0:
        return None
    return abs(by - ty) / scale / 10.0


def _measure_front(img_bgr, factor, res) -> list[float]:
    det = detect_markers(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY))
    res.markers_found.extend(det)
    if not any(k in det for k in _FRONT_ANY):
        res.warnings.append("no_front_markers_detected")
        return []
    res.views.append("front")
    mask = segment_garment(img_bgr, [d["center"] for d in det.values()])

    band_scales: list[float] = []
    for marker, band in _FRONT_BAND_MARKER.items():
        if marker not in det:
            res.warnings.append(f"{band}_marker_not_detected")
            continue
        c, scale = det[marker]["center"], det[marker]["px_per_mm"]
        r = _BAND_REFINE[band]
        snap = _refine_band(mask, int(c[1]), int(c[0]), scale, r["dy_lo_mm"], r["dy_hi_mm"], r["mode"])
        if snap:
            _, xl, xr = snap
        else:
            ext = _band_extent(mask, int(c[1]), int(c[0]))
            if not ext:
                res.warnings.append(f"no_silhouette_at_{band}")
                continue
            xl, xr = ext
        band_scales.append(scale)
        res.add(band, circular_girth_cm((xr - xl) / scale / 10.0, factor), "girth")

    if "FSH_L" in det and "FSH_R" in det:
        sw = _span_width_cm(mask, det, "FSH_L", "FSH_R")
        if sw:
            res.add("shoulder_width", sw, "width")
    fl = _vertical_length_cm(det, ("FSH_L", "FSH_R"), "FH")
    if fl:
        res.add("front_length", fl, "length")
    return band_scales


def _measure_back(img_bgr, factor, res) -> None:
    det = detect_markers(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY))
    res.markers_found.extend(det)
    if not any(k in det for k in _BACK_MARKERS):
        res.warnings.append("no_back_markers_detected")
        return
    res.views.append("back")
    mask = segment_garment(img_bgr, [d["center"] for d in det.values()])

    if "BSH_L" in det and "BSH_R" in det:
        bw = _span_width_cm(mask, det, "BSH_L", "BSH_R")
        if bw:
            res.add("back_shoulder_width", bw, "width")
    if "UB" in det:
        c = det["UB"]["center"]
        ext = _band_extent(mask, int(c[1]), int(c[0]))
        if ext:
            res.add("upper_back_width", (ext[1] - ext[0]) / det["UB"]["px_per_mm"] / 10.0, "width")
    bl = _vertical_length_cm(det, ("BSH_L", "BSH_R"), "LB")
    if bl:
        res.add("back_length", bl, "length")


def _finalize(res: VestMeasurement, band_scales: list[float]) -> None:
    res.markers_found = sorted(set(res.markers_found))
    if band_scales:
        res.scale_px_per_mm = round(float(np.median(band_scales)), 2)
    girths = [m for m in res.measurements.values() if m["kind"] == "girth"]
    if len(band_scales) >= 2 and res.scale_px_per_mm:
        spread = float(np.std(band_scales)) / res.scale_px_per_mm
        res.confidence = round(max(0.0, min(1.0, 1.0 - 4.0 * spread)), 2)
        if spread > 0.15:
            res.warnings.append("high_scale_spread_oblique_capture")
    elif len(band_scales) == 1:
        res.confidence = 0.5
    if not girths:
        res.warnings.append("no_girths_measured")


# --- public entry -------------------------------------------------------------
def measure_vest_views(
    front_bgr: np.ndarray | None = None,
    back_bgr: np.ndarray | None = None,
    calibration_factor: float = VEST_CALIBRATION_FACTOR,
) -> VestMeasurement:
    """
    Measure the full vest set from front (+ optional back) photos.

    Returns girths (bust/waist/hip), shoulder width + front length from the front,
    and back shoulder/upper-back width + back length from the back. Degrades
    gracefully: any band whose marker is missing is skipped with a warning.
    """
    res = VestMeasurement(calibration_factor=calibration_factor)
    band_scales: list[float] = []
    if front_bgr is not None and front_bgr.size:
        band_scales = _measure_front(front_bgr, calibration_factor, res)
    if back_bgr is not None and back_bgr.size:
        _measure_back(back_bgr, calibration_factor, res)
    if not res.views:
        res.warnings.append("no_markers_detected")
    _finalize(res, band_scales)
    return res


def measure_vest_front(
    img_bgr: np.ndarray,
    calibration_factor: float = VEST_CALIBRATION_FACTOR,
) -> VestMeasurement:
    """Front-only convenience entry (kept for existing callers)."""
    return measure_vest_views(front_bgr=img_bgr, calibration_factor=calibration_factor)


def _read(src) -> np.ndarray | None:
    if src is None:
        return None
    return src if isinstance(src, np.ndarray) else cv2.imread(str(src))


def measure_vest(
    front: str | Path | np.ndarray | None,
    back: str | Path | np.ndarray | None = None,
    calibration_factor: float = VEST_CALIBRATION_FACTOR,
) -> dict:
    """Convenience wrapper: paths or BGR arrays for front (+ optional back)."""
    fimg, bimg = _read(front), _read(back)
    if fimg is None and bimg is None:
        return VestMeasurement(warnings=["cannot_read_images"]).to_dict()
    return measure_vest_views(fimg, bimg, calibration_factor).to_dict()
