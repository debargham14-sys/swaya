#!/usr/bin/env python3
"""
Perspective-flatten a tilted DSV photo using a ChArUco sticker (F0–F3).

Usage:
    python notebooks/rectify_dsv_photo.py front.jpg F1
    python notebooks/rectify_dsv_photo.py front.jpg F1 --out flat_F1.png

The output image is a fronto-parallel view where the board is square and
measurements in the crop are in real mm (at the chosen px/mm resolution).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

_NOTEBOOKS = Path(__file__).resolve().parent
_ROOT = _NOTEBOOKS.parent
sys.path.insert(0, str(_NOTEBOOKS))

import charuco_dsv_lib as lib  # noqa: E402


def _orient(img, rotate: str):
    if rotate == "auto" and img.shape[1] > img.shape[0]:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if rotate == "cw90":
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if rotate == "ccw90":
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img


def main() -> int:
    parser = argparse.ArgumentParser(description="Rectify tilted DSV photo via ChArUco homography")
    parser.add_argument("image", type=Path, help="Input photo path")
    parser.add_argument("slot", choices=["F0", "F1", "F2", "F3"], help="Which sticker to anchor on")
    parser.add_argument("--out", type=Path, default=None, help="Output PNG (default: <image>_<slot>_flat.png)")
    parser.add_argument("--px-per-mm", type=float, default=3.0, help="Output resolution")
    parser.add_argument("--upscale", type=float, default=3.0, help="Detection upscale factor")
    parser.add_argument(
        "--rotate",
        choices=["none", "auto", "cw90", "ccw90"],
        default="auto",
        help="Rotate portrait phone photos (default: auto if landscape)",
    )
    args = parser.parse_args()

    img = cv2.imread(str(args.image))
    if img is None:
        print(f"Could not read {args.image}", file=sys.stderr)
        return 1
    img = _orient(img, args.rotate)

    spec = lib.CharucoRectifySpec(px_per_mm=args.px_per_mm, upscale_for_detect=args.upscale)
    try:
        view = lib.auto_rectify_dsv_photo(img, args.slot, spec=spec)
    except ValueError as exc:
        print(f"Rectify failed: {exc}", file=sys.stderr)
        return 1

    out = args.out or args.image.with_name(f"{args.image.stem}_{args.slot}_flat.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), view.image_bgr, [cv2.IMWRITE_PNG_COMPRESSION, 1])

    print(f"Slot: {view.slot_name}")
    print(f"Corners: {view.calibration.charuco_corners}")
    print(f"Output: {out} ({view.image_bgr.shape[1]}x{view.image_bgr.shape[0]} px)")
    print(f"Board: {view.board_mm[0]:.0f} x {view.board_mm[1]:.0f} mm")
    print(f"Scale: {view.mm_per_px_out:.4f} mm/px in output")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
