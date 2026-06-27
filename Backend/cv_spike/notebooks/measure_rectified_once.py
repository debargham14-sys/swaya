#!/usr/bin/env python3
"""Run one ChArUco-rectified DSV measurement on front/side/back photos."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_NOTEBOOKS = Path(__file__).resolve().parent
_ROOT = _NOTEBOOKS.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_NOTEBOOKS))

import dsv_probe_lib as probe  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="ChArUco-rectified DSV measurement (one shot)")
    parser.add_argument(
        "--dir",
        type=Path,
        default=_ROOT / "spike_data/user_capture/sticker_worn_v2",
        help="Folder with front.png, side.png, back.png",
    )
    parser.add_argument("--height", type=float, default=170.0, help="Subject height cm")
    parser.add_argument("--out", type=Path, default=_ROOT / "assets/dsv_charuco/rectified")
    args = parser.parse_args()

    paths = {v: args.dir / f"{v}.png" for v in ("front", "side", "back")}
    missing = [k for k, p in paths.items() if not p.is_file()]
    if missing:
        print(f"Missing: {missing} in {args.dir}", file=sys.stderr)
        return 1

    result = probe.run_charuco_rectified_measurement(
        paths,
        height_cm=args.height,
        out_dir=args.out,
    )

    print("=== ChArUco rectified measurement ===")
    print(f"Front marker: {result.get('front_slot')}")
    for view, sc in result.get("scales", {}).items():
        print(f"  {view}: {sc['method']}  cm/px={sc['cm_per_px']:.5f}")
    if result.get("band_widths_cm"):
        print("Band tape widths (cm):", result["band_widths_cm"])
        for lv, det in result.get("band_width_detail", {}).items():
            print(
                f"  {lv}: {det.get('width_in')} in  "
                f"[{det.get('edge_source')}/{det.get('scale_source')}]"
            )
    elif result.get("rectified_widths_cm"):
        print("Rectified front widths:", result["rectified_widths_cm"])
    print("\nGirths (cm):")
    for lv, g in result.get("girths_cm", {}).items():
        m = next(x for x in result["measures"] if x["level"] == lv)
        print(
            f"  {lv:10s}  girth={g:6.1f}  "
            f"W={m.get('width_cm')}  D={m.get('depth_cm')}  [{m.get('source')}]"
        )
    if result.get("outputs"):
        print(f"\nRectified PNG: {result['outputs'].get('rectified_png')}")
    print(f"JSON: {args.out / 'measurement_result.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
