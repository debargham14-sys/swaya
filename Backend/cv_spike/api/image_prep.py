"""Prepare phone uploads: EXIF orientation, then resize for CV."""

from __future__ import annotations

import os
from pathlib import Path

import cv2


def max_image_edge() -> int:
    raw = os.environ.get("SCAN_MAX_IMAGE_EDGE", "1536").strip()
    try:
        return max(640, min(int(raw), 2560))
    except ValueError:
        return 1280


def normalize_orientation(path: Path) -> tuple[Path, list[str]]:
    """Apply EXIF rotation so OpenCV/MediaPipe see upright bodies (critical on iPhone)."""
    warnings: list[str] = []
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return path, warnings

    try:
        with Image.open(path) as im:
            rotated = ImageOps.exif_transpose(im)
            if rotated is None:
                rotated = im
            rgb = rotated.convert("RGB")
            out = path.with_suffix(".jpg")
            rgb.save(out, format="JPEG", quality=92, optimize=True)
            if out != path and path.exists():
                path.unlink()
            return out, warnings
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"{path.stem}:exif_failed:{str(exc)[:80]}")
    return path, warnings


def downscale_scan_paths(paths: dict[str, Path], *, max_edge: int | None = None) -> list[str]:
    """Shrink large phone photos in place; returns warning strings."""
    edge = max_edge if max_edge is not None else max_image_edge()
    warnings: list[str] = []
    for view, path in paths.items():
        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if img is None:
            warnings.append(f"{view}:unreadable")
            continue
        h, w = img.shape[:2]
        longest = max(h, w)
        if longest <= edge:
            continue
        scale = edge / float(longest)
        resized = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        ext = path.suffix.lower() if path.suffix else ".jpg"
        if ext not in (".jpg", ".jpeg", ".png"):
            ext = ".jpg"
        out = path.with_suffix(ext)
        quality = 88 if ext in (".jpg", ".jpeg") else 3
        if ext in (".jpg", ".jpeg"):
            cv2.imwrite(str(out), resized, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        else:
            cv2.imwrite(str(out), resized)
        if out != path and path.exists():
            path.unlink()
            paths[view] = out
        warnings.append(f"{view}:downscaled_{w}x{h}_to_{resized.shape[1]}x{resized.shape[0]}")
    return warnings


def prepare_scan_paths(paths: dict[str, Path]) -> list[str]:
    """EXIF upright + downscale — run on every upload before measurement."""
    warnings: list[str] = []
    for view in list(paths.keys()):
        out, w = normalize_orientation(paths[view])
        paths[view] = out
        warnings.extend(w)
    warnings.extend(downscale_scan_paths(paths))
    return warnings


def vest_max_image_edge() -> int:
    """Higher cap for the ChArUco vest flow — small markers need the resolution."""
    raw = os.environ.get("VEST_MAX_IMAGE_EDGE", "3500").strip()
    try:
        return max(2000, min(int(raw), 6000))
    except ValueError:
        return 3500


def prepare_vest_paths(paths: dict[str, Path]) -> list[str]:
    """
    EXIF upright + a gentle downscale that keeps ChArUco markers detectable.

    Unlike prepare_scan_paths (which shrinks to ~1.5k px for silhouette/pose),
    the vest markers are small, so cap at VEST_MAX_IMAGE_EDGE (default 3500 px).
    The normalized photos are what we both measure and archive for re-processing.
    """
    warnings: list[str] = []
    for view in list(paths.keys()):
        out, w = normalize_orientation(paths[view])
        paths[view] = out
        warnings.extend(w)
    warnings.extend(downscale_scan_paths(paths, max_edge=vest_max_image_edge()))
    return warnings
