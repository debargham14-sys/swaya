"""Run MediaPipe pose + segmentation (subprocess on macOS avoids GL crashes)."""

from __future__ import annotations

import base64
import json
import os
import sys
import threading
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def resolve_pose_model_path() -> Path:
    """Find pose_landmarker.task in Docker (/app/models) or local checkout."""
    env = os.environ.get("POSE_MODEL_PATH", "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p
    for candidate in (
        ROOT / "models" / "pose_landmarker.task",
        Path("/app/models/pose_landmarker.task"),
    ):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "pose_landmarker.task not found — rebuild Docker image or set POSE_MODEL_PATH"
    )


def pose_model_status() -> dict:
    try:
        p = resolve_pose_model_path()
        return {"ok": True, "path": str(p), "size_bytes": p.stat().st_size}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


_POSE_MODEL: Path | None = None
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

_landmarker = None
_landmarker_lock = threading.Lock()


def _pose_min_detection_confidence() -> float:
    raw = os.environ.get("POSE_MIN_DETECTION_CONFIDENCE", "0.4").strip()
    try:
        return max(0.2, min(float(raw), 0.9))
    except ValueError:
        return 0.4


def _pose_mask_threshold() -> float:
    raw = os.environ.get("POSE_MASK_THRESHOLD", "0.4").strip()
    try:
        return max(0.2, min(float(raw), 0.8))
    except ValueError:
        return 0.4


def _detect(bgr: np.ndarray) -> dict:
    import mediapipe as mp
    from mediapipe.tasks import python as mptp
    from mediapipe.tasks.python import vision

    global _landmarker, _POSE_MODEL
    with _landmarker_lock:
        if _landmarker is None:
            if _POSE_MODEL is None:
                _POSE_MODEL = resolve_pose_model_path()
            base = mptp.BaseOptions(model_asset_path=str(_POSE_MODEL))
            opts = vision.PoseLandmarkerOptions(
                base_options=base,
                running_mode=vision.RunningMode.IMAGE,
                output_segmentation_masks=True,
                num_poses=1,
                min_pose_detection_confidence=_pose_min_detection_confidence(),
                min_pose_presence_confidence=_pose_min_detection_confidence(),
            )
            _landmarker = vision.PoseLandmarker.create_from_options(opts)
        landmarker = _landmarker

    rgb = np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    res = landmarker.detect(mp_img)
    h, w = bgr.shape[:2]
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
        mask = (m > _pose_mask_threshold()).astype(np.uint8) * 255
        ok, buf = cv2.imencode(".png", mask)
        if ok:
            out["mask_b64"] = base64.b64encode(buf.tobytes()).decode("ascii")
            out["mask_shape"] = [int(mask.shape[0]), int(mask.shape[1])]
    return out


def run_on_bgr(bgr: np.ndarray) -> dict:
    if bgr is None or bgr.size == 0:
        return {"error": "empty_image"}
    try:
        return _detect(bgr)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:240]}


def run_on_path(path: str) -> dict:
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        return {"error": f"unreadable:{path}"}
    return run_on_bgr(img)


def warmup() -> dict:
    """Load MediaPipe pose model once (call on API startup)."""
    tiny = __import__("numpy").zeros((64, 48, 3), dtype=__import__("numpy").uint8)
    return run_on_bgr(tiny)


def main(argv: list[str] | None = None) -> int:
    path = (argv or sys.argv)[1]
    print(json.dumps(run_on_path(path)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
