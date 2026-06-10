#!/usr/bin/env python3
"""
Turn DSV vest marker photos into real garment widths + first-pass girths.

Pipeline per view:
  1. detect ChArUco markers (DICT_4X4_250) -> landmark centers + local px/mm
  2. segment the garment silhouette (GrabCut seeded from the marker hull)
  3. at each band row (bust/waist/hip on front; the side markers on profiles)
     measure the garment edge-to-edge extent through the centerline
  4. width(front) + depth(side) -> ellipse girth (Ramanujan)

Honest scope: the vest is loosely draped on a dress form and shot obliquely, so
widths are GARMENT widths (>= body) and side bands are not perfectly height-
aligned to the front bands. Treat girths as first-pass; recapture square-on /
body-conforming for tailoring-grade numbers.

Usage (from Backend/cv_spike):
    python notebooks/measure_dsv_silhouette.py --dir /Users/debargha/Desktop/swaya/assets/DSV_1/jpg
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

MARKER_MM = 9.0
IDS_PER_BOARD = 10
NAMES = ["FSH_L", "FSH_R", "FB", "FW", "FH", "SR_U", "SR_L",
         "SL_U", "SL_L", "BSH_L", "BSH_R", "UB", "MB", "LB"]


def detect(gray: np.ndarray) -> dict[str, dict]:
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_250)
    det = cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters())
    corners, ids, _ = det.detectMarkers(gray)
    acc: dict[int, dict] = {}
    if ids is None:
        return {}
    for m, i in zip(corners, ids.flatten()):
        b = int(i) // IDS_PER_BOARD
        if b >= len(NAMES):
            continue
        side = float(np.mean([np.linalg.norm(m[0][k] - m[0][(k + 1) % 4]) for k in range(4)]))
        acc.setdefault(b, {"sides": [], "ctrs": []})
        acc[b]["sides"].append(side)
        acc[b]["ctrs"].append(m[0].mean(axis=0))
    return {
        NAMES[b]: {
            "center": np.mean(v["ctrs"], axis=0),
            "px_per_mm": float(np.median(v["sides"]) / MARKER_MM),
        }
        for b, v in acc.items()
    }


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    ff = mask.copy()
    z = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(ff, z, (0, 0), 1)
    return (mask | (1 - ff)).astype(np.uint8)


def segment_garment(img: np.ndarray, centers: list[np.ndarray]) -> np.ndarray:
    """
    Garment mask from GRID-TEXTURE energy (the 1 cm grid lives only on the vest),
    keeping the blob that contains the marker centroid. Robust to a background
    whose colour matches the fabric, unlike colour/GrabCut.
    """
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

    cen = (np.mean(centers, axis=0) * s).astype(int)
    cen = np.clip(cen, [0, 0], [small.shape[1] - 1, small.shape[0] - 1])
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    lid = int(lab[cen[1], cen[0]])
    if lid == 0 and n > 1:
        lid = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    m = (lab == lid).astype(np.uint8) if lid else m
    m = _fill_holes(m)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8))
    return cv2.resize(m, (w, h), interpolation=cv2.INTER_NEAREST)


def band_extent(mask: np.ndarray, y: int, cx: int, half: int = 18) -> tuple[int, int] | None:
    """Edge-to-edge extent of the garment run that contains the centreline cx."""
    h, w = mask.shape
    y = int(np.clip(y, half, h - half - 1))
    row = (mask[y - half:y + half].sum(axis=0) > half).astype(np.uint8)
    xs = np.where(row)[0]
    if len(xs) < 10:
        return None
    splits = np.where(np.diff(xs) > 8)[0]
    groups = np.split(xs, splits + 1)
    cx = int(np.clip(cx, 0, w - 1))
    best = min(groups, key=lambda g: 0 if g[0] <= cx <= g[-1] else min(abs(g[0] - cx), abs(g[-1] - cx)))
    return int(best[0]), int(best[-1])


# Per-band anthropometric refinement: snap from the marker anchor to the true
# extremum within a bounded window (mm), so the result is robust to where the
# marker was taped. (dy_lo_mm, dy_hi_mm) is the search window relative to the
# marker row (+ = below); mode picks widest ('max') or narrowest ('min').
BAND_REFINE = {
    "bust":  {"dy_lo_mm": -35, "dy_hi_mm": 35,  "mode": "max"},
    "waist": {"dy_lo_mm": -35, "dy_hi_mm": 35,  "mode": "min"},
    "hip":   {"dy_lo_mm": -20, "dy_hi_mm": 75,  "mode": "max"},
}


def refine_band(mask: np.ndarray, y0: int, cx: int, px_per_mm: float,
                dy_lo_mm: float, dy_hi_mm: float, mode: str) -> tuple[int, int, int] | None:
    """
    Scan rows in [y0+dy_lo, y0+dy_hi] and return (y, left, right) at a ROBUST
    extremum: the 90th-pct width for 'max' bands (bust/hip) or 10th-pct for
    'min' (waist). Percentile, not hard min/max, so a single noisy row (e.g. a
    fabric gather) can't dominate.
    """
    lo = int(y0 + dy_lo_mm * px_per_mm)
    hi = int(y0 + dy_hi_mm * px_per_mm)
    rows: list[tuple[int, int, int]] = []
    widths: list[int] = []
    for y in range(min(lo, hi), max(lo, hi) + 1, 6):
        ext = band_extent(mask, y, cx)
        if ext:
            rows.append((y, ext[0], ext[1]))
            widths.append(ext[1] - ext[0])
    if not rows:
        return None
    target = np.percentile(widths, 90 if mode == "max" else 10)
    idx = int(np.argmin(np.abs(np.array(widths) - target)))
    return rows[idx]


def ellipse_circ_mm(width_mm: float, depth_mm: float) -> float:
    a, b = width_mm / 2.0, depth_mm / 2.0
    h = ((a - b) / (a + b)) ** 2 if (a + b) else 0.0
    return float(np.pi * (a + b) * (1 + 3 * h / (10 + np.sqrt(4 - 3 * h))))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=Path("/Users/debargha/Desktop/swaya/assets/DSV_1/jpg"))
    args = ap.parse_args()
    out = args.dir.parent / "measure"
    out.mkdir(parents=True, exist_ok=True)

    front = {"FB": "bust", "FW": "waist", "FH": "hip"}
    widths: dict[str, dict] = {}     # band -> {width_mm, scale}
    depths: dict[str, list] = {"upper": [], "lower": []}

    for p in sorted(args.dir.glob("*.jpg")):
        img = cv2.imread(str(p))
        det = detect(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        if not det:
            continue
        centers = [d["center"] for d in det.values()]
        mask = segment_garment(img, centers)
        vis = img.copy()
        vis[mask > 0] = (0.6 * vis[mask > 0] + 0.4 * np.array([0, 160, 0])).astype(np.uint8)

        is_front = "FB" in det and "FW" in det and "FH" in det
        is_side = any(k in det for k in ("SL_U", "SL_L", "SR_U", "SR_L")) and not is_front

        if is_front:
            for mk, band in front.items():
                if mk not in det:
                    continue
                c = det[mk]["center"]
                scale = det[mk]["px_per_mm"]
                r = BAND_REFINE[band]
                snap = refine_band(mask, int(c[1]), int(c[0]), scale,
                                   r["dy_lo_mm"], r["dy_hi_mm"], r["mode"])
                if snap:
                    yv, xl, xr = snap
                else:
                    ext = band_extent(mask, int(c[1]), int(c[0]))
                    if not ext:
                        continue
                    yv, (xl, xr) = int(c[1]), ext
                wmm = (xr - xl) / scale
                widths[band] = {"width_mm": wmm, "scale": scale,
                                "snapped_mm": round((yv - int(c[1])) / scale, 1)}
                cv2.line(vis, (xl, yv), (xr, yv), (0, 60, 230), 4, cv2.LINE_AA)
                cv2.putText(vis, f"{band} W={wmm/10:.1f}cm", (xl, yv - 12),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 40, 210), 3, cv2.LINE_AA)
        elif is_side:
            for mk in ("SL_U", "SR_U", "SL_L", "SR_L"):
                if mk not in det:
                    continue
                slot = "upper" if mk.endswith("_U") else "lower"
                c = det[mk]["center"]
                ext = band_extent(mask, int(c[1]), int(c[0]))
                if not ext:
                    continue
                dmm = (ext[1] - ext[0]) / det[mk]["px_per_mm"]
                depths[slot].append(dmm)
                yv = int(c[1])
                cv2.line(vis, (ext[0], yv), (ext[1], yv), (230, 60, 0), 4, cv2.LINE_AA)
                cv2.putText(vis, f"{slot} D={dmm/10:.1f}cm", (ext[0], yv - 12),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.4, (210, 40, 0), 3, cv2.LINE_AA)

        cv2.imwrite(str(out / f"{p.stem}_silhouette.jpg"), vis, [cv2.IMWRITE_JPEG_QUALITY, 85])

    up = float(np.median(depths["upper"])) if depths["upper"] else None
    lo = float(np.median(depths["lower"])) if depths["lower"] else None
    band_depth = {
        "bust": up,
        "hip": lo,
        "waist": (np.mean([up, lo]) if up and lo else (up or lo)),
    }

    print("\nGARMENT WIDTHS (front, edge-to-edge) and DEPTHS (side, front-back):")
    girths = {}
    for band in ("bust", "waist", "hip"):
        wmm = widths.get(band, {}).get("width_mm")
        dmm = band_depth.get(band)
        line = f"  {band:5s}  width={wmm/10:.1f}cm" if wmm else f"  {band:5s}  width=NA"
        if dmm:
            line += f"  depth={dmm/10:.1f}cm"
        if wmm and dmm:
            g = ellipse_circ_mm(wmm, dmm)
            girths[band] = round(g / 10.0, 1)
            line += f"  ->  GIRTH ~ {g/10:.1f}cm ({g/25.4:.1f}in)"
        print(line)

    result = {
        "widths_cm": {k: round(v["width_mm"] / 10, 1) for k, v in widths.items()},
        "depths_cm": {k: round(v / 10, 1) for k, v in band_depth.items() if v},
        "girths_cm": girths,
        "method": "front edge-to-edge width + side front-back depth -> Ramanujan ellipse",
        "caveats": [
            "garment loosely draped on a size-12 dress form (widths >= body)",
            "side bands (upper/lower) not height-aligned to bust/waist/hip",
            "oblique single shots -> some foreshortening (see marker/grid scale spread)",
        ],
    }
    (out / "girths.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nOverlays + girths.json -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
