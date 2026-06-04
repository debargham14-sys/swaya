"""Resize uploads before CV (keeps Render/Railway scans within memory and time limits)."""

from __future__ import annotations

import os
from pathlib import Path

import cv2


def max_image_edge() -> int:
    raw = os.environ.get("SCAN_MAX_IMAGE_EDGE", "1280").strip()
    try:
        return max(640, min(int(raw), 2560))
    except ValueError:
        return 1280


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
