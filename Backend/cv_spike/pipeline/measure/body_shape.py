"""
Estimate torso girths from body core (pose skeleton + height), not outer clothing.

When a loose top hides the waist or side depth is dominated by hanging fabric, we
infer body width from the shoulder–hip landmark span and reuse bust-level body
depth ratios for lower torso slices.
"""

from __future__ import annotations

from pipeline.measure import markerless as ml
from pipeline.measure.slice_measure import SliceSample, _side_y_for_torso_frac

# Anthropometric torso fractions (shoulder -> hip) for body landmarks
BODY_FRAC = {
    "bust": 0.28,
    "underbust": 0.48,
    "waist": 0.62,
    "hip": 0.92,
}

# Female-average front:back depth as fraction of width
_DEFAULT_DEPTH_RATIO = 0.72
_WAIST_DEPTH_RATIO = 0.68
_WAIST_DEPTH_CAP = 0.72  # max depth/width at waist (avoids shirt/skirt bulk on side)
_WAIST_BAND = (0.54, 0.74)


def infer_torso_depth_ratio(
    side: ml._ProfileView | None,
    side_pose: dict | None,
    side_top: int,
    side_stat: int,
    samples: list[SliceSample],
) -> float:
    """
    Typical body front:back ratio from upper/mid torso side slices.
    Caps side depth when a loose shirt inflates the profile.
    """
    if side is None or not side.cm_per_px:
        return _WAIST_DEPTH_RATIO
    ratios: list[float] = []
    for frac in (0.22, 0.28, 0.38, 0.48):
        band = [s for s in samples if abs(s.torso_frac - frac) < 0.035]
        if not band:
            continue
        w = band[0].width_cm
        if w <= 0:
            continue
        y = _side_y_for_torso_frac(side_pose, side_top, side_stat, frac)
        dpx = ml._largest_run_width(side.mask, y)
        if dpx <= 0:
            continue
        raw = dpx * side.cm_per_px
        ratio = min(raw / w, 0.90)
        if 0.52 <= ratio <= 0.90:
            ratios.append(ratio)
    if ratios:
        return float(__import__("numpy").median(ratios))
    return _WAIST_DEPTH_RATIO


def skeleton_span_px(pose: dict, y: int, margin: float = 1.0) -> int:
    """Interpolated shoulder-to-hip landmark span at row y (pixels)."""
    sx = sorted([pose["l_shoulder"][0], pose["r_shoulder"][0]])
    hx = sorted([pose["l_hip"][0], pose["r_hip"][0]])
    sy = (pose["l_shoulder"][1] + pose["r_shoulder"][1]) / 2.0
    hy = (pose["l_hip"][1] + pose["r_hip"][1]) / 2.0
    t = 0.0 if hy == sy else (y - sy) / (hy - sy)
    t = float(__import__("numpy").clip(t, -0.2, 1.2))
    left = sx[0] + t * (hx[0] - sx[0])
    right = sx[1] + t * (hx[1] - sx[1])
    return max(1, int((right - left) * margin))


def body_width_px(
    fmask,
    y: int,
    fcx: int,
    pose: dict | None,
    loose_top: bool,
) -> int:
    """Body-core width: skeleton span + flesh margin, capped by clipped silhouette."""
    bounds = ml._torso_x_bounds(pose, y, margin=1.05) if pose else None
    sil_px = ml._central_run_width(fmask, y, fcx, bounds)
    if not pose or not loose_top:
        return sil_px
    skel = skeleton_span_px(pose, y, margin=1.0)
    # Flesh beyond biacromial / biiliac line (~10–22% per side for torso)
    body_px = int(skel * 1.18)
    return min(sil_px, max(body_px, int(skel * 1.06)))


def detect_loose_top(samples: list[SliceSample]) -> bool:
    """
    Loose untucked top: front width falls steadily from chest to hip with no waist pinch.
    """
    mid = [s for s in samples if 0.35 <= s.torso_frac <= 0.88 and not s.flare]
    if len(mid) < 4:
        return False

    bust_band = [s for s in samples if 0.15 <= s.torso_frac <= 0.42 and not s.flare]
    waist_band = [s for s in mid if _WAIST_BAND[0] <= s.torso_frac <= _WAIST_BAND[1]]
    if bust_band and waist_band:
        bust_w = max(s.width_cm for s in bust_band)
        waist_w = min(s.width_cm for s in waist_band)
        # Fitted / shaped torso: clear pinch between bust and anatomical waist band.
        if waist_w < bust_w * 0.85:
            return False

    decreasing = sum(
        1 for i in range(len(mid) - 1) if mid[i].width_cm >= mid[i + 1].width_cm * 0.97
    )
    if decreasing < max(2, len(mid) - 3):
        return False
    # No clear waist notch: min width is in lower half of band
    min_s = min(mid, key=lambda s: s.width_cm)
    return min_s.torso_frac >= 0.68


def _bust_depth_ratio(samples: list[SliceSample]) -> float | None:
    upper = [s for s in samples if 0.15 <= s.torso_frac <= 0.38 and s.depth_cm]
    if not upper:
        return None
    best = max(upper, key=lambda s: s.torso_frac)
    if best.width_cm <= 0:
        return None
    ratio = best.depth_cm / best.width_cm
    if 0.45 <= ratio <= 0.88:
        return ratio
    return None


def body_depth_cm(
    side: ml._ProfileView | None,
    y_side: int,
    body_width_cm: float,
    depth_ratio: float | None,
    *,
    waist_band: bool = False,
) -> float:
    """Side depth capped to body plausibility; fall back to torso ratio prior."""
    ratio = depth_ratio if depth_ratio else (_WAIST_DEPTH_RATIO if waist_band else _DEFAULT_DEPTH_RATIO)
    if waist_band:
        ratio = min(ratio, _WAIST_DEPTH_RATIO)
    if side is None or not side.cm_per_px:
        return body_width_cm * ratio
    dpx = ml._largest_run_width(side.mask, y_side)
    if dpx <= 0:
        return body_width_cm * ratio
    raw = dpx * side.cm_per_px
    cap = _WAIST_DEPTH_CAP if waist_band else 0.86
    lo = 0.48 * body_width_cm
    if raw >= lo and raw <= body_width_cm * cap:
        return raw
    return body_width_cm * ratio


def apply_body_core(
    samples: list[SliceSample],
    fmask,
    fcx,
    pose,
    side,
    side_pose,
    side_top: int,
    side_stat: int,
    cm_f: float,
    loose: bool,
) -> float | None:
    """Rewrite sample width/depth/girth using body-core model. Returns bust depth ratio."""
    ratio = _bust_depth_ratio(samples) or infer_torso_depth_ratio(
        side, side_pose, side_top, side_stat, samples,
    )
    for s in samples:
        y_side = _side_y_for_torso_frac(side_pose, side_top, side_stat, s.torso_frac)
        sil_w_cm = s.width_cm
        if s.torso_frac < 0.52:
            s.depth_cm = body_depth_cm(side, y_side, sil_w_cm, ratio)
        elif s.torso_frac <= 0.72:
            # Waist: keep front silhouette width; conservative body depth only.
            s.depth_cm = body_depth_cm(
                side, y_side, sil_w_cm, ratio, waist_band=True,
            )
        else:
            skel_cm = skeleton_span_px(pose, s.y) * cm_f
            blended = max(skel_cm * 1.32, sil_w_cm * 0.88)
            s.width_cm = round(min(sil_w_cm, blended), 2)
            s.depth_cm = body_depth_cm(side, y_side, s.width_cm, ratio)
        s.girth_cm = ml._ellipse_girth_cm(s.width_cm, s.depth_cm)
    return ratio


def _sample_at_frac(samples: list[SliceSample], frac: float) -> SliceSample | None:
    if not samples:
        return None
    return min(samples, key=lambda s: abs(s.torso_frac - frac))


def levels_from_body_shape(
    samples: list[SliceSample],
    loose_top: bool,
) -> tuple[list[ml.LevelMeasure], list[str]]:
    """Pick girth levels from body-core slice curve."""
    warnings: list[str] = []
    if loose_top:
        warnings.append("body_shape:loose_top_skeleton_estimate")

    usable = [s for s in samples if not s.flare] or samples

    bust = _sample_at_frac(usable, BODY_FRAC["bust"])
    if bust is None or bust.torso_frac < 0.12:
        candidates = [s for s in usable if 0.12 <= s.torso_frac <= 0.42]
        bust = max(candidates, key=lambda s: s.girth_cm) if candidates else usable[0]

    underbust = _sample_at_frac(usable, BODY_FRAC["underbust"])
    waist_band = [
        s for s in usable
        if _WAIST_BAND[0] <= s.torso_frac <= _WAIST_BAND[1] and not s.flare
    ]
    waist = min(waist_band, key=lambda s: s.girth_cm) if waist_band else _sample_at_frac(
        usable, BODY_FRAC["waist"],
    )
    hip = _sample_at_frac(usable, BODY_FRAC["hip"])

    hip_girth = hip.girth_cm if hip else None
    if waist and hip and hip.girth_cm < waist.girth_cm:
        hip_girth = round(waist.girth_cm * 1.08, 1)
        warnings.append("body_shape:hip_from_waist_ratio")

    picks = {"bust": bust, "underbust": underbust, "waist": waist, "hip": hip}
    levels: list[ml.LevelMeasure] = []
    for name, pick in picks.items():
        if pick is None:
            warnings.append(f"{name}_no_body_slice")
            continue
        girth = hip_girth if name == "hip" and hip_girth and pick is hip else pick.girth_cm
        # Only lift impossibly thin waist on loose tops (not fitted clothing).
        if loose_top and name == "waist" and bust and girth < bust.girth_cm * 0.72:
            girth = round(bust.girth_cm * 0.72, 1)
            warnings.append("body_shape:waist_floor_loose_top")
        conf = 0.78 if pick.depth_cm else 0.62
        if loose_top and name in ("waist", "hip"):
            conf = 0.55
        levels.append(
            ml.LevelMeasure(
                name=name,
                y_px=pick.y,
                width_cm=round(pick.width_cm, 1),
                depth_cm=round(pick.depth_cm, 1) if pick.depth_cm else None,
                girth_cm=round(girth, 1),
                confidence=conf,
            )
        )
    return levels, warnings
