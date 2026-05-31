#!/usr/bin/env python3
"""Try 4D-Humans mesh recovery + girth measurement on a front photo."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import smpl_backend
from pipeline.measure_engine import measure, print_result


def main() -> None:
    p = argparse.ArgumentParser(description="Try 4D-Humans (HMR2.0) body mesh + girths")
    p.add_argument("front", type=Path, help="Front photo (full body)")
    p.add_argument("--side", type=Path, default=None)
    p.add_argument("--back", type=Path, default=None)
    p.add_argument("--height", type=float, default=None, help="Height cm (or use --ref)")
    p.add_argument("--ref", choices=("aruco", "card", "a4"), default="aruco")
    p.add_argument("--ref-mm", type=float, default=50.0)
    args = p.parse_args()

    status = smpl_backend.backend_status()
    print("Backends:", status)
    if not status["four_d_humans"]:
        raise SystemExit("4D-Humans not installed. Run: bash scripts/setup_4dhumans.sh")
    if not status["smpl_cached"] and not status["smpl_vendor"]:
        raise SystemExit("SMPL model missing. See models/smpl/README.md")

    r = measure(
        args.height,
        None,
        front=args.front,
        side=args.side,
        back=args.back,
        prefer="four_d_humans",
        ref_kind=args.ref if args.height is None else None,
        ref_marker_mm=args.ref_mm,
    )
    print_result(r)


if __name__ == "__main__":
    main()
