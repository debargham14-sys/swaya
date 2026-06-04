"""
Horizontal slice-sweep girth estimation from front + side silhouettes.

Scans torso rows between pose shoulder and hip landmarks, builds a girth curve,
then picks bust / underbust / waist / hip from local extrema. Scanning stops at
the hip line and flare rows are rejected so flared skirts do not shrink hip or
inflate waist measurements.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pipeline.measure import markerless as ml

GIRTH_LEVELS = ("bust", "underbust", "waist", "hip")

# Torso fractions (shoulder -> hip) for level search bands
_BANDS = {
    "bust": (0.12, 0.40),
    "underbust": (0.40, 0.55),
    "waist": (0.58, 0.76),
    "hip": (0.84, 1.00),
}


@dataclass
class SliceSample:
    y: int
    torso_frac: float
    width_cm: float
    depth_cm: float | None
    girth_cm: float
    flare: bool


def _pose_torso(pose: dict | None) -> tuple[float, float] | None:
    if not pose:
        return None
    sh = (pose["l_shoulder"][1] + pose["r_shoulder"][1]) / 2.0
    hip = (pose["l_hip"][1] + pose["r_hip"][1]) / 2.0
    if hip <= sh + 8:
        return None
    return sh, hip


def _side_y_for_torso_frac(side_pose: dict | None, side_top: int, side_stat: int, frac: float) -> int:
    torso = _pose_torso(side_pose)
    if torso is not None:
        sh, hip = torso
        return int(sh + frac * (hip - sh))
    return int(side_top + frac * side_stat)


def _depth_cm_at_y(
    side: ml._ProfileView | None,
    y_side: int,
    width_cm: float,
) -> float | None:
    if side is None or not side.cm_per_px:
        return None
    dpx = ml._largest_run_width(side.mask, y_side)
    if dpx <= 0:
        return None
    depth = dpx * side.cm_per_px
    if depth < 0.45 * width_cm or depth > 0.78 * width_cm:
        return None
    return depth


def _girth(width_cm: float, depth_cm: float | None) -> float:
    if depth_cm and depth_cm > 1:
        return ml._ellipse_girth_cm(width_cm, depth_cm)
    return ml._ellipse_girth_cm(width_cm, 0.68 * width_cm)


def _mark_flare_rows(samples: list[SliceSample]) -> None:
    """Flag rows where front width expands like a skirt flare below the waist band."""
    if len(samples) < 6:
        return
    widths = np.array([s.width_cm for s in samples])
    fracs = np.array([s.torso_frac for s in samples])
    # Waist band reference: narrowest width in mid torso (0.45–0.82)
    mid = (fracs >= 0.45) & (fracs <= 0.82)
    if not mid.any():
        ref = float(np.median(widths))
    else:
        ref = float(np.min(widths[mid]))
    ref = max(ref, 1.0)
    # Flare: substantially wider than torso reference in lower torso / near hip
    for s in samples:
        if s.torso_frac >= 0.78 and s.width_cm > ref * 1.12:
            s.flare = True
        # Rapid widening between consecutive slices in lower third
        idx = samples.index(s)
        if idx > 0 and s.torso_frac >= 0.70:
            prev = samples[idx - 1]
            if s.width_cm > prev.width_cm * 1.06 and s.width_cm > ref * 1.05:
                s.flare = True


def scan_torso_slices(
    fmask: np.ndarray,
    fpose: dict | None,
    fcx: int,
    cm_per_px_front: float,
    side: ml._ProfileView | None,
    cm_per_px_side: float | None,
) -> tuple[list[SliceSample], list[str]]:
    """Sweep horizontal slices across the pose torso band only (shoulder..hip)."""
    warnings: list[str] = []
    torso = _pose_torso(fpose)
    if torso is None:
        top, bottom = ml._vertical_extent(fmask)
        stat = max(1, bottom - top)
        # Narrow band (shoulder..upper hip) avoids measuring flared skirts when pose fails.
        sh, hip = float(top + 0.14 * stat), float(top + 0.42 * stat)
        warnings.append("slice_sweep:pose_fallback_torso_band")
    else:
        sh, hip = torso

    side_pose = side.pose if side else None
    side_top = side.top if side else 0
    side_stat = max(1, (side.bottom - side.top)) if side else 1

    y0 = int(sh + 0.05 * (hip - sh))
    y1 = int(hip)  # never scan below hip landmark (skirt lives below)
    step = max(1, int((y1 - y0) / 80))
    samples: list[SliceSample] = []

    for y in range(y0, y1 + 1, step):
        frac = (y - sh) / max(1.0, hip - sh)
        frac = float(np.clip(frac, 0.0, 1.0))
        bounds = ml._torso_x_bounds(fpose, y)
        wpx = ml._central_run_width(fmask, y, fcx, bounds)
        if wpx <= 0:
            continue
        width_cm = wpx * cm_per_px_front
        y_side = _side_y_for_torso_frac(side_pose, side_top, side_stat, frac)
        depth_cm = _depth_cm_at_y(side, y_side, width_cm)
        samples.append(
            SliceSample(
                y=y,
                torso_frac=frac,
                width_cm=width_cm,
                depth_cm=depth_cm,
                girth_cm=_girth(width_cm, depth_cm),
                flare=False,
            )
        )

    if not samples:
        warnings.append("slice_sweep:no_samples")
        return samples, warnings

    _mark_flare_rows(samples)
    valid = [s for s in samples if not s.flare]
    if len(valid) < len(samples) * 0.5:
        warnings.append("slice_sweep:heavy_flare_clipped")
    elif any(s.flare for s in samples):
        warnings.append("slice_sweep:flare_rows_excluded")
    return samples, warnings


def _pick_in_band(
    samples: list[SliceSample],
    lo: float,
    hi: float,
    mode: str,
    mid_frac: float | None = None,
) -> SliceSample | None:
    band = [s for s in samples if lo <= s.torso_frac <= hi and not s.flare]
    if not band:
        band = [s for s in samples if lo <= s.torso_frac <= hi]
    if not band:
        return None
    if mode == "max":
        return max(band, key=lambda s: s.girth_cm)
    if mode == "min":
        return min(band, key=lambda s: s.girth_cm)
    target = mid_frac if mid_frac is not None else (lo + hi) / 2.0
    return min(band, key=lambda s: abs(s.torso_frac - target))


def levels_from_sweep(samples: list[SliceSample]) -> tuple[list[ml.LevelMeasure], list[str]]:
    """Map slice curve to named girth levels."""
    warnings: list[str] = []
    usable = [s for s in samples if not s.flare]
    if len(usable) < 4:
        usable = samples
        warnings.append("slice_sweep:used_flare_rows")

    picks = {
        "bust": _pick_in_band(usable, *_BANDS["bust"], "max"),
        "underbust": _pick_in_band(usable, *_BANDS["underbust"], "mid", mid_frac=0.48),
        "waist": _pick_in_band(usable, *_BANDS["waist"], "min"),
        "hip": _pick_in_band(usable, *_BANDS["hip"], "max"),
    }
    levels: list[ml.LevelMeasure] = []
    for name, pick in picks.items():
        if pick is None:
            warnings.append(f"{name}_no_slice")
            continue
        conf = 0.72 if pick.depth_cm else 0.55
        if pick.flare:
            conf *= 0.5
        levels.append(
            ml.LevelMeasure(
                name=name,
                y_px=pick.y,
                width_cm=round(pick.width_cm, 1),
                depth_cm=round(pick.depth_cm, 1) if pick.depth_cm else None,
                girth_cm=round(pick.girth_cm, 1),
                confidence=conf,
            )
        )
    return levels, warnings


def estimate_torso_girths(
    fmask,
    fpose,
    fcx: int,
    cm_per_px_front: float,
    side: ml._ProfileView | None,
    cm_per_px_side: float | None,
) -> tuple[list[SliceSample], list[ml.LevelMeasure], list[str]]:
    """
    Slice-sweep with automatic switch to pose skeleton body-core when clothing
    hides the waist (monotonic shirt taper or hip < waist).
    """
    from pipeline.measure.body_shape import (
        apply_body_core,
        detect_loose_top,
        levels_from_body_shape,
    )

    samples, warnings = scan_torso_slices(
        fmask, fpose, fcx, cm_per_px_front, side, cm_per_px_side,
    )
    cloth_levels, w2 = levels_from_sweep(samples)
    warnings.extend(w2)

    loose_top = detect_loose_top(samples)
    cloth = {lv.name: lv for lv in cloth_levels}
    skirt_flare = (
        cloth.get("hip") and cloth.get("waist")
        and cloth["hip"].girth_cm is not None
        and cloth["waist"].girth_cm is not None
        and cloth["hip"].girth_cm < cloth["waist"].girth_cm
    )
    if skirt_flare:
        warnings.append("slice_sweep:skirt_flare_hip_adjusted")

    if loose_top and fpose:
        side_pose = side.pose if side else None
        side_top = side.top if side else 0
        side_stat = max(1, (side.bottom - side.top)) if side else 1
        apply_body_core(
            samples, fmask, fcx, fpose, side, side_pose,
            side_top, side_stat, cm_per_px_front, True,
        )
        levels, w3 = levels_from_body_shape(samples, True)
        warnings.extend(w3)
        warnings.append("body_shape:mode_active")
    else:
        levels = list(cloth_levels)
        if skirt_flare and cloth.get("waist") and cloth.get("hip"):
            w_cm = cloth["waist"].girth_cm
            hip_lv = next(l for l in levels if l.name == "hip")
            if hip_lv.girth_cm < w_cm:
                hip_lv.girth_cm = round(w_cm * 1.06, 1)
                hip_lv.confidence *= 0.7
    return samples, levels, warnings
