#!/usr/bin/env python3
"""
demo_random_usd.py

A zero-input starting point: writes a series of random numpy arrays
out as an animated USD (usdc) particle file, using the same export
function as sap_flow_usd.py.  Drop the result into Blender to check
that your USD playback pipeline works before hooking up real data.

Usage:
    python demo_random_usd.py                      # 100 frames, 500 points
    python demo_random_usd.py --frames 240 --points 200 --out demo.usdc
"""

import argparse
from pathlib import Path

import numpy as np

from sap_flow_usd import export_usd


def random_time_steps(frames: int, points: int, seed: int | None = None):
    """One (P, 3) random position array per frame.

    (The original notebook prototyped with exactly this:
    np.random.random((100, 500, 3)).)
    """
    rng = np.random.default_rng(seed)
    arr = rng.random((frames, points, 3), dtype=np.float32)
    return [frame for frame in arr]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frames", type=int, default=100,
                    help="number of frames (default: 100)")
    ap.add_argument("--points", type=int, default=500,
                    help="particles per frame (default: 500)")
    ap.add_argument("--out", default="demo_random.usdc", type=Path,
                    help="output USD file (default: demo_random.usdc)")
    ap.add_argument("--fps", type=float, default=24,
                    help="frame rate (default: 24)")
    ap.add_argument("--seed", type=int, default=None,
                    help="random seed for reproducible output")
    args = ap.parse_args()

    time_steps = random_time_steps(args.frames, args.points, args.seed)
    export_usd(time_steps, args.out, fps=args.fps)
    print(f"done: {args.out}")


if __name__ == "__main__":
    main()
