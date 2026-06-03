"""Run MediaPipe pose + segmentation in an isolated process (macOS GL crash workaround)."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
_POSE_MODEL = ROOT / "models" / "pose_landmarker.task"
_POSE_IDX = {
    "nose": 0,
    "l_shoulder": 11,
    "r_shoulder": 12,
    "l_hip": 23,
    "r_hip": 24,
    "l_ankle": 27,
    "r_ankle": 28,
    "l_heel": 29,
    "r_heel": 30,
    "l_foot": 31,
    "r_foot": 32,
}


def run_on_path(path: str) -> dict:
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        return {"error": f"unreadable:{path}"}
    import mediapipe as mp
    from mediapipe.tasks import python as mptp
    from mediapipe.tasks.python import vision

    rgb = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    base = mptp.BaseOptions(model_asset_path=str(_POSE_MODEL))
    opts = vision.PoseLandmarkerOptions(
        base_options=base,
        running_mode=vision.RunningMode.IMAGE,
        output_segmentation_masks=True,
        num_poses=1,
    )
    with vision.PoseLandmarker.create_from_options(opts) as lmk:
        res = lmk.detect(mp_img)
    h, w = img.shape[:2]
    out: dict = {"landmarks": None, "mask_b64": None, "mask_shape": None}
    if res.pose_landmarks:
        lm = res.pose_landmarks[0]
        out["landmarks"] = {
            name: [int(lm[idx].x * w), int(lm[idx].y * h)]
            for name, idx in _POSE_IDX.items()
        }
    if res.segmentation_masks:
        m = np.array(res.segmentation_masks[0].numpy_view(), copy=True, dtype=np.float32)
        if m.ndim == 3:
            m = m[:, :, 0]
        mask = (m > 0.5).astype(np.uint8) * 255
        ok, buf = cv2.imencode(".png", mask)
        if ok:
            out["mask_b64"] = base64.b64encode(buf.tobytes()).decode("ascii")
            out["mask_shape"] = [int(mask.shape[0]), int(mask.shape[1])]
    return out


def main(argv: list[str] | None = None) -> int:
    path = (argv or sys.argv)[1]
    print(json.dumps(run_on_path(path)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
