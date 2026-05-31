#!/usr/bin/env python3
"""Measure with explicit height (+ optional weight). Default: photo silhouette estimator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.measure_engine import measure, print_result


def main() -> None:
    p = argparse.ArgumentParser(description="Height-based body measurement (photo default)")
    p.add_argument("--front", type=Path, required=True)
    p.add_argument("--back", type=Path, required=True)
    p.add_argument("--side", type=Path, required=True)
    p.add_argument("--height", type=float, required=True, help="Height in cm")
    p.add_argument("--weight", type=float, default=None, help="Weight in kg (optional)")
    p.add_argument(
        "--prefer",
        choices=("four_d_humans", "photo", "auto", "smplx"),
        default="photo",
    )
    p.add_argument("--tape-in", type=str, default=None)
    args = p.parse_args()

    r = measure(
        args.height,
        args.weight,
        front=args.front,
        back=args.back,
        side=args.side,
        prefer=args.prefer,
        tape_in=args.tape_in,
    )
    print_result(r)


if __name__ == "__main__":
    main()
