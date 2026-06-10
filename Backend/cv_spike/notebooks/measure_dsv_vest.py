#!/usr/bin/env python3
"""
Measure the DSV vest from marker photos (front / back / left / right).

Scale comes from two independent fiducials printed on the vest:
  1. the ChArUco marker boards (inner ArUco markers are 9 mm) -> per-marker px/mm
  2. the 1 cm x 1 cm grid woven into the fabric -> px per 10 mm via local FFT

Each marker id is mapped to a body landmark (id // 10), so we can report
landmark-to-landmark distances. NOTE: these are oblique single-shot photos of a
dress form, so distances along a receding line are foreshortened (under-read).
Treat results as first-pass estimates with the scale spread as the error signal.

Usage (from Backend/cv_spike):
    python notebooks/measure_dsv_vest.py --dir /Users/debargha/Desktop/swaya/assets/DSV_1/jpg
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

MARKER_MM = 9.0          # ChArUco inner ArUco markerLength
GRID_MM = 10.0           # woven 1 cm fiducial squares
IDS_PER_BOARD = 10
NAMES = ["FSH_L", "FSH_R", "FB", "FW", "FH", "SR_U", "SR_L",
         "SL_U", "SL_L", "BSH_L", "BSH_R", "UB", "MB", "LB"]
REGION = {n: ("front" if n.startswith("F") else "side" if n.startswith("S")
              else "back") for n in NAMES}

# Landmark pairs to measure, per dominant view.
FRONT_PAIRS = [("FSH_L", "FSH_R", "shoulder width (marker span)"),
               ("FB", "FW", "bust->waist drop"),
               ("FW", "FH", "waist->hip drop"),
               ("FB", "FH", "bust->hip drop")]
BACK_PAIRS = [("BSH_L", "BSH_R", "back shoulder span"),
              ("UB", "MB", "upper->mid back"),
              ("MB", "LB", "mid->lower back"),
              ("UB", "LB", "upper->lower back")]
SIDE_PAIRS_L = [("SL_U", "SL_L", "left side upper->lower")]
SIDE_PAIRS_R = [("SR_U", "SR_L", "right side upper->lower")]


def detect_blocks(gray: np.ndarray) -> dict[int, dict]:
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_250)
    det = cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters())
    corners, ids, _ = det.detectMarkers(gray)
    blocks: dict[int, dict] = {}
    if ids is None:
        return blocks
    for m, i in zip(corners, ids.flatten()):
        b = int(i) // IDS_PER_BOARD
        if b >= len(NAMES):
            continue
        side = float(np.mean([np.linalg.norm(m[0][k] - m[0][(k + 1) % 4]) for k in range(4)]))
        blocks.setdefault(b, {"sides": [], "ctrs": []})
        blocks[b]["sides"].append(side)
        blocks[b]["ctrs"].append(m[0].mean(axis=0))
    out = {}
    for b, v in blocks.items():
        out[b] = {
            "name": NAMES[b],
            "region": REGION[NAMES[b]],
            "n": len(v["sides"]),
            "center": np.mean(v["ctrs"], axis=0),
            "px_per_mm": float(np.median(v["sides"]) / MARKER_MM),
        }
    return out


def grid_period_px(gray: np.ndarray, lo: int = 25, hi: int = 110) -> float | None:
    """Estimate the dominant grid period (px) over sampled fabric patches via FFT."""
    h, w = gray.shape
    periods: list[float] = []
    step = 320
    for y in range(step, h - step, step):
        for x in range(step, w - step, step):
            patch = gray[y - 128:y + 128, x - 128:x + 128].astype(np.float32)
            if patch.std() < 12:                      # skip flat / non-grid regions
                continue
            patch = patch - patch.mean()
            patch *= cv2.createHanningWindow((patch.shape[1], patch.shape[0]), cv2.CV_32F)
            mag = np.abs(np.fft.fftshift(np.fft.fft2(patch)))
            cy, cx = np.array(mag.shape) // 2
            mag[cy - 3:cy + 4, cx - 3:cx + 4] = 0     # kill DC
            yy, xx = np.unravel_index(np.argmax(mag), mag.shape)
            r = float(np.hypot(yy - cy, xx - cx))
            if r < 1:
                continue
            period = patch.shape[0] / r
            if lo <= period <= hi:
                periods.append(period)
    if len(periods) < 4:
        return None
    return float(np.median(periods))


def measure_view(name: str, img: np.ndarray) -> dict:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blocks = detect_blocks(gray)
    by_name = {b["name"]: b for b in blocks.values()}
    regions = [b["region"] for b in blocks.values()]
    view = max(set(regions), key=regions.count) if regions else "unknown"
    side_kind = None
    if view == "side":
        side_kind = "left" if "SL_U" in by_name or "SL_L" in by_name else "right"

    grid_px = grid_period_px(gray)
    grid_px_per_mm = (grid_px / GRID_MM) if grid_px else None
    marker_scales = [b["px_per_mm"] for b in blocks.values()]
    marker_px_per_mm = float(np.median(marker_scales)) if marker_scales else None

    pairs = {"front": FRONT_PAIRS, "back": BACK_PAIRS}.get(view, [])
    if view == "side":
        pairs = SIDE_PAIRS_L if side_kind == "left" else SIDE_PAIRS_R

    measures = []
    for a, b, label in pairs:
        if a in by_name and b in by_name:
            pa, pb = by_name[a]["center"], by_name[b]["center"]
            dpx = float(np.hypot(*(pa - pb)))
            scale = np.mean([by_name[a]["px_per_mm"], by_name[b]["px_per_mm"]])
            mm = dpx / scale
            measures.append({
                "label": label, "from": a, "to": b,
                "px": round(dpx, 1), "cm_markers": round(mm / 10.0, 1),
                "cm_grid": round(dpx / grid_px_per_mm / 10.0, 1) if grid_px_per_mm else None,
            })

    return {
        "file": name, "view": view, "side": side_kind,
        "markers_found": sorted(by_name),
        "scale_px_per_mm": {
            "markers_median": round(marker_px_per_mm, 2) if marker_px_per_mm else None,
            "grid_fft": round(grid_px_per_mm, 2) if grid_px_per_mm else None,
            "marker_spread": round(float(np.std(marker_scales)), 2) if marker_scales else None,
        },
        "measurements": measures,
        "_blocks": by_name,
    }


def annotate(img: np.ndarray, result: dict, out_path: Path) -> None:
    vis = img.copy()
    by_name = result["_blocks"]
    for nm, b in by_name.items():
        c = tuple(int(v) for v in b["center"])
        cv2.circle(vis, c, 14, (0, 200, 0), 3)
        cv2.putText(vis, nm, (c[0] + 16, c[1]), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 180, 0), 3, cv2.LINE_AA)
    for m in result["measurements"]:
        pa = tuple(int(v) for v in by_name[m["from"]]["center"])
        pb = tuple(int(v) for v in by_name[m["to"]]["center"])
        cv2.line(vis, pa, pb, (0, 80, 255), 3, cv2.LINE_AA)
        mid = ((pa[0] + pb[0]) // 2, (pa[1] + pb[1]) // 2)
        txt = f"{m['cm_markers']}cm" + (f" / grid {m['cm_grid']}" if m["cm_grid"] else "")
        cv2.putText(vis, txt, mid, cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 60, 220), 3, cv2.LINE_AA)
    cv2.imwrite(str(out_path), vis, [cv2.IMWRITE_JPEG_QUALITY, 88])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=Path("/Users/debargha/Desktop/swaya/assets/DSV_1/jpg"))
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    out_dir = args.out or args.dir.parent / "measure"
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = []
    for p in sorted(args.dir.glob("*.jpg")):
        img = cv2.imread(str(p))
        res = measure_view(p.name, img)
        annotate(img, res, out_dir / f"{p.stem}_measured.jpg")
        res.pop("_blocks")
        summary.append(res)
        sc = res["scale_px_per_mm"]
        print(f"\n{p.name}: view={res['view']}{'/' + res['side'] if res['side'] else ''}  "
              f"markers={res['markers_found']}")
        print(f"  scale px/mm: markers={sc['markers_median']} grid={sc['grid_fft']} "
              f"(marker spread +-{sc['marker_spread']})")
        for m in res["measurements"]:
            g = f", grid {m['cm_grid']} cm" if m["cm_grid"] else ""
            print(f"    {m['label']:28s} {m['cm_markers']} cm{g}")

    (out_dir / "measurements.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nAnnotated images + measurements.json -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
