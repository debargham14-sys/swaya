#!/usr/bin/env python3
"""
Generate the 13 uniquely-identifiable ChArUco markers for the worn DSV sizing vest.

Each marker is a known-size ChArUco board (a metric scale reference) taped at a
named body position. All boards share one dictionary (DICT_4X4_250) but occupy
non-overlapping marker-id ranges, so detection identifies exactly which body
landmark each board belongs to -> real height + body measurements for fit.

Positions (13): front shoulder L/R, front waist, front hip, right side upper/lower,
left side upper/lower, back shoulder L/R, upper/mid/lower back.

Usage (from Backend/cv_spike):
    python notebooks/generate_vest_markers.py
    python notebooks/generate_vest_markers.py --dpi 600 --out assets/dsv_charuco/vest_markers

Print vest_markers_a4_<dpi>dpi.pdf at 100% scale (no fit-to-page).
Each board must measure 60 mm x 48 mm after printing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_NOTEBOOKS = Path(__file__).resolve().parent
_ROOT = _NOTEBOOKS.parent
sys.path.insert(0, str(_NOTEBOOKS))

import charuco_dsv_lib as lib  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the 13 DSV vest ChArUco markers")
    parser.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "assets/dsv_charuco/vest_markers",
        help="Output directory",
    )
    parser.add_argument("--dpi", type=float, default=300.0, help="Print resolution (300 or 600)")
    parser.add_argument(
        "--square-mm",
        type=float,
        default=lib.VEST_MARKER_SQUARE_MM,
        help="ChArUco square size in mm (default 12)",
    )
    parser.add_argument(
        "--dict",
        dest="dict_name",
        default=lib.VEST_MARKER_DICT,
        help="ArUco dictionary shared by all boards (default DICT_4X4_250)",
    )
    args = parser.parse_args()

    sheet = lib.CharucoStickerSheetSpec(
        dpi=args.dpi,
        cols=lib.VEST_MARKER_COLS,
        rows=lib.VEST_MARKER_ROWS,
        square_mm=args.square_mm,
        marker_mm=args.square_mm * 0.75,
    )
    meta = lib.generate_vest_marker_stickers(sheet, args.out, dict_name=args.dict_name)

    print(f"DSV vest ChArUco markers generated ({meta['marker_count']} boards, {meta['dict']})")
    print(f"  Sheet PDF: {meta['outputs']['sheet_pdf']}")
    for name, board in meta["boards"].items():
        lo, hi = board["id_range"]
        ok = "OK" if board["corners_detected"] >= board["corners_expected"] else "FAIL"
        print(
            f"  {name:6s} {board['region']:5s} ids {lo:>3d}-{hi:<3d} "
            f"corners={board['corners_detected']}/{board['corners_expected']} "
            f"[{ok}]  {board['description']}"
        )
    print(f"  Validation: {'PASS' if meta['validation_ok'] else 'FAIL'}")
    print()
    print(meta["print_instructions"])
    return 0 if meta["validation_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
