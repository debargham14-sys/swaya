#!/usr/bin/env python3
"""
Render a placement guide showing WHERE the 13 ChArUco markers go on the DSV vest.

Draws a front and a back vest silhouette with each real ChArUco board pasted at
its body position (side-seam markers shown on the front view's edges), labelled
with its code + description. This is a layout reference, not a print master --
use generate_vest_markers.py for the boards you actually print and tape on.

Usage (from Backend/cv_spike):
    python notebooks/render_vest_marker_layout.py
    python notebooks/render_vest_marker_layout.py --out assets/dsv_charuco/vest_markers/layout.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

_NOTEBOOKS = Path(__file__).resolve().parent
_ROOT = _NOTEBOOKS.parent
sys.path.insert(0, str(_NOTEBOOKS))

import charuco_dsv_lib as lib  # noqa: E402

FABRIC = (232, 230, 225)      # BGR light fabric
OUTLINE = (70, 70, 70)
GUIDE = (150, 150, 150)
TEXT = (40, 40, 40)
TITLE = (25, 25, 25)

PANEL_W, PANEL_H = 560, 820
MARKER_PX = 74                # pasted board width on the diagram

# Vest silhouette outline (normalised torso coords), V-neck front.
_FRONT_NECK = [(0.42, 0.05), (0.50, 0.17), (0.58, 0.05)]
_BACK_NECK = [(0.42, 0.05), (0.50, 0.10), (0.58, 0.05)]
_TORSO_SIDES = [
    (0.78, 0.07), (0.87, 0.21), (0.80, 0.30), (0.85, 0.35),   # R shoulder->armhole->side
    (0.74, 0.55), (0.83, 0.80), (0.78, 0.93),                 # R waist->hip->hem
    (0.22, 0.93), (0.17, 0.80), (0.26, 0.55),                 # L hem->hip->waist
    (0.15, 0.35), (0.20, 0.30), (0.13, 0.21), (0.22, 0.07),   # L side->armhole->shoulder
]

# Marker code -> (normalised x, normalised y) per view.
FRONT_POS = {
    "FSH_L": (0.30, 0.11),
    "FSH_R": (0.70, 0.11),
    "FB": (0.50, 0.33),
    "FW": (0.50, 0.55),
    "FH": (0.50, 0.87),
    "SL_U": (0.14, 0.35),
    "SL_L": (0.16, 0.63),
    "SR_U": (0.86, 0.35),
    "SR_L": (0.84, 0.63),
}
BACK_POS = {
    "BSH_L": (0.30, 0.11),
    "BSH_R": (0.70, 0.11),
    "UB": (0.50, 0.30),
    "MB": (0.50, 0.53),
    "LB": (0.50, 0.75),
}
# Faint horizontal level guides on the front view (label, normalised y).
FRONT_LEVELS = [("BUST", 0.33), ("WAIST", 0.55), ("HIP (widest)", 0.87)]


def _torso_xy(nx: float, ny: float, x0: int, y0: int, tw: int, th: int) -> tuple[int, int]:
    return int(x0 + nx * tw), int(y0 + ny * th)


def _draw_silhouette(panel: np.ndarray, neck, x0: int, y0: int, tw: int, th: int) -> None:
    pts = [_torso_xy(nx, ny, x0, y0, tw, th) for nx, ny in _TORSO_SIDES]
    poly = np.array(pts, np.int32)
    cv2.fillPoly(panel, [poly], FABRIC)
    cv2.polylines(panel, [poly], True, OUTLINE, 2, cv2.LINE_AA)
    neck_pts = [_torso_xy(nx, ny, x0, y0, tw, th) for nx, ny in neck]
    cv2.polylines(panel, [np.array(neck_pts, np.int32)], False, OUTLINE, 2, cv2.LINE_AA)


def _paste_marker(panel: np.ndarray, name: str, nx: float, ny: float,
                  x0: int, y0: int, tw: int, th: int, boards: dict) -> None:
    board = boards[name]
    bw = MARKER_PX
    bh = int(round(bw * board.shape[0] / board.shape[1]))
    small = cv2.resize(board, (bw, bh), interpolation=cv2.INTER_AREA)
    cx, cy = _torso_xy(nx, ny, x0, y0, tw, th)
    px, py = cx - bw // 2, cy - bh // 2
    h, w = panel.shape[:2]
    px = max(2, min(w - bw - 2, px))
    py = max(2, min(h - bh - 2, py))
    panel[py : py + bh, px : px + bw] = small
    cv2.rectangle(panel, (px - 2, py - 2), (px + bw + 1, py + bh + 1), (90, 90, 90), 1, cv2.LINE_AA)
    cv2.putText(panel, name, (px, py + bh + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, TEXT, 1, cv2.LINE_AA)


def _make_panel(title: str, neck, positions: dict, boards: dict, levels=None) -> np.ndarray:
    panel = np.full((PANEL_H, PANEL_W, 3), 255, np.uint8)
    x0, y0 = 70, 90
    tw, th = PANEL_W - 140, PANEL_H - 150
    _draw_silhouette(panel, neck, x0, y0, tw, th)
    if levels:
        for label, ny in levels:
            y = int(y0 + ny * th)
            for x in range(x0 - 10, x0 + tw + 10, 14):
                cv2.line(panel, (x, y), (x + 7, y), GUIDE, 1, cv2.LINE_AA)
            cv2.putText(panel, label, (x0 + tw - 6, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.42, GUIDE, 1, cv2.LINE_AA)
    for name, (nx, ny) in positions.items():
        _paste_marker(panel, name, nx, ny, x0, y0, tw, th, boards)
    cv2.putText(panel, title, (x0, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.85, TITLE, 2, cv2.LINE_AA)
    return panel


def main() -> int:
    parser = argparse.ArgumentParser(description="Render DSV vest marker placement guide")
    parser.add_argument(
        "--out", type=Path,
        default=_ROOT / "assets/dsv_charuco/vest_markers/vest_marker_layout.png",
    )
    args = parser.parse_args()

    boards = {}
    for spec in lib.dsv_vest_marker_set():
        bgr, _, _, _ = lib._render_charuco_ids_board_bgr(
            spec.cols, spec.rows, spec.square_mm, spec.marker_mm,
            lib.VEST_MARKER_DICT, spec.id_offset, px_per_mm=6.0,
        )
        boards[spec.name] = bgr

    front = _make_panel("FRONT", _FRONT_NECK, FRONT_POS, boards, FRONT_LEVELS)
    back = _make_panel("BACK (worn)", _BACK_NECK, BACK_POS, boards)
    gap = np.full((PANEL_H, 4, 3), 220, np.uint8)
    body = np.hstack([front, gap, back])

    header = np.full((70, body.shape[1], 3), 255, np.uint8)
    cv2.putText(header, "DSV vest - ChArUco marker placement (14 markers)",
                (70, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.9, TITLE, 2, cv2.LINE_AA)
    note = np.full((40, body.shape[1], 3), 255, np.uint8)
    cv2.putText(note, "Side-seam markers (SL/SR upper+lower) shown on the front view edges. Tape flat at each labelled spot.",
                (70, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.5, TEXT, 1, cv2.LINE_AA)
    out_img = np.vstack([header, body, note])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(args.out), out_img, [cv2.IMWRITE_PNG_COMPRESSION, 1])
    print(f"Vest marker layout written: {args.out}")
    print(f"  {out_img.shape[1]}x{out_img.shape[0]} px  -  14 markers (9 front+sides, 5 back)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
