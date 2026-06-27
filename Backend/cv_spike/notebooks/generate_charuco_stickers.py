#!/usr/bin/env python3
"""
Generate printable ChArUco stickers (F0–F3) for taping onto a worn DSV vest.

Usage (from Backend/cv_spike):
    python notebooks/generate_charuco_stickers.py
    python notebooks/generate_charuco_stickers.py --dpi 600 --out assets/dsv_charuco/stickers

Print charuco_stickers_a4_300dpi.pdf at 100% scale (no fit-to-page).
Each board must measure 60 mm × 48 mm after printing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_NOTEBOOKS = Path(__file__).resolve().parent
_ROOT = _NOTEBOOKS.parent
sys.path.insert(0, str(_NOTEBOOKS))

import charuco_dsv_lib as lib  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate DSV ChArUco sticker sheet (F0–F3)")
    parser.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "assets/dsv_charuco/stickers",
        help="Output directory",
    )
    parser.add_argument("--dpi", type=float, default=300.0, help="Print resolution (300 or 600)")
    parser.add_argument(
        "--square-mm",
        type=float,
        default=12.0,
        help="ChArUco square size in mm (default 12 = production DSV)",
    )
    parser.add_argument(
        "--slots",
        nargs="+",
        default=["F0", "F1", "F2", "F3"],
        help="Which markers to generate",
    )
    args = parser.parse_args()

    spec = lib.CharucoStickerSheetSpec(
        dpi=args.dpi,
        square_mm=args.square_mm,
        marker_mm=args.square_mm * 0.75,
        slots=tuple(args.slots),
    )
    meta = lib.generate_charuco_sticker_sheet(spec, args.out)

    print("DSV ChArUco stickers generated")
    print(f"  Sheet PDF: {meta['outputs']['sheet_pdf']}")
    print(f"  Sheet PNG: {meta['outputs']['sheet_png']}")
    for name, board in meta["boards"].items():
        ok = "OK" if board["corners_detected"] >= board["corners_expected"] else "FAIL"
        print(
            f"  {name}: {board['board_mm'][0]:.0f}×{board['board_mm'][1]:.0f} mm "
            f"dict={board['dict']} corners={board['corners_detected']}/{board['corners_expected']} [{ok}]"
        )
    print(f"  Validation: {'PASS' if meta['validation_ok'] else 'FAIL'}")
    print()
    print(meta["print_instructions"])
    return 0 if meta["validation_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
