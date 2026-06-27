#!/usr/bin/env python3
"""
Pose-aware segmentation backend for DSV vest measurement.

Why this exists: the grid-texture silhouette in ``vest_charuco.segment_garment``
floods when the vest sits on a low-contrast (white-on-white) background. A real
person-segmentation model fixes that. MediaPipe's PoseLandmarker gives BOTH a
clean person mask AND body landmarks in one pass (the repo already ships
``models/pose_landmarker.task``), so we use it to:

  1. segment the person (mask robust to background) -> replaces grid-texture
  2. place bust/waist/hip rows from landmarks / markers
  3. EXCLUDE the arms from the torso width by clipping the row search window to
     the gap between the two arm centerlines (shoulder->elbow->wrist polylines)

Honest limit: when an arm is pressed flat against the torso (no gap), the clip
lands at the arm, not the true body edge — so the result is flagged low
confidence. No 2D segmenter can see a body edge hidden behind an arm; an A-pose
is still required for tape-grade width. This module makes the GOOD captures
accurate and the BAD ones honest, instead of silently wrong.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

# MediaPipe BlazePose landmark indices
L_SH, R_SH = 11, 12
L_EL, R_EL = 13, 14
L_WR, R_WR = 15, 16
L_HIP, R_HIP = 23, 24
_ARM_L = (L_SH, L_EL, L_WR)
_ARM_R = (R_SH, R_EL, R_WR)

_DEFAULT_MODEL = Path(__file__).resolve().parent.parent / "models" / "pose_landmarker.task"


def mediapipe_available(model_path: str | Path = _DEFAULT_MODEL) -> bool:
    try:
        import mediapipe  # noqa: F401
        from mediapipe.tasks.python import vision  # noqa: F401
    except Exception:
        return False
    return Path(model_path).is_file()


def detect_pose_and_mask(img_bgr: np.ndarray, model_path: str | Path = _DEFAULT_MODEL):
    """Return (person_mask uint8 HxW, landmarks_px dict idx->(x,y)) or (None, None)."""
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision

    h, w = img_bgr.shape[:2]
    opts = vision.PoseLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(model_path)),
        output_segmentation_masks=True,
    )
    with vision.PoseLandmarker.create_from_options(opts) as lm:
        mpimg = mp.Image(image_format=mp.ImageFormat.SRGB,
                         data=cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
        res = lm.detect(mpimg)
    if not res.pose_landmarks:
        return None, None
    mask = np.squeeze(res.segmentation_masks[0].numpy_view() > 0.5).astype(np.uint8)
    if mask.shape != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
    P = res.pose_landmarks[0]
    lms = {i: (int(P[i].x * w), int(P[i].y * h)) for i in range(len(P))}
    return mask, lms


def _arm_x_at(lms: dict, arm: tuple, y: int) -> float | None:
    """Interpolate an arm centerline's x at image row y along shoulder->elbow->wrist."""
    pts = [lms[i] for i in arm if i in lms]
    if len(pts) < 2:
        return None
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        lo, hi = sorted([y0, y1])
        if lo <= y <= hi and y1 != y0:
            t = (y - y0) / (y1 - y0)
            return x0 + t * (x1 - x0)
    # y outside the polyline span -> clamp to nearest endpoint
    return float(min(pts, key=lambda p: abs(p[1] - y))[0])


def torso_extent(mask: np.ndarray, lms: dict, y: int, cx: int,
                 half: int = 12) -> tuple[int, int, bool] | None:
    """
    Edge-to-edge torso extent at row y from the person mask, with the arms
    clipped out via the arm-centerline window. Returns (left, right, arm_clipped)
    where arm_clipped flags that an arm bounded the window (so the edge may be
    the arm, not the body -> lower confidence).
    """
    h, w = mask.shape
    y = int(np.clip(y, half, h - half - 1))
    row = (mask[y - half:y + half].sum(axis=0) > half).astype(np.uint8)

    xl_arm = _arm_x_at(lms, _ARM_R, y)   # person-right arm -> image left
    xr_arm = _arm_x_at(lms, _ARM_L, y)   # person-left arm  -> image right
    lo = int(xl_arm) if xl_arm is not None and xl_arm < cx else 0
    hi = int(xr_arm) if xr_arm is not None and xr_arm > cx else w - 1
    clipped = (lo > 0) or (hi < w - 1)

    win = np.zeros_like(row)
    win[max(0, lo):min(w, hi + 1)] = 1
    xs = np.where(row & win)[0]
    if len(xs) < 8:
        return None
    # contiguous run containing / nearest the centerline (gap tolerant)
    groups = np.split(xs, np.where(np.diff(xs) > 12)[0] + 1)
    cx = int(np.clip(cx, 0, w - 1))
    best = min(groups, key=lambda g: 0 if g[0] <= cx <= g[-1]
               else min(abs(g[0] - cx), abs(g[-1] - cx)))
    return int(best[0]), int(best[-1]), clipped
