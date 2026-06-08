"""
Body-type-aware girth estimation (sex, build, clothing).

Lifted from the DSV measurement probe notebook so the same logic runs in
measure_engine, the API, and interactive probes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from pipeline.measure import markerless as ml
from pipeline.measure.body_shape import apply_body_core, detect_loose_top
from pipeline.measure.slice_measure import SliceSample, estimate_torso_girths, scan_torso_slices

GIRTH_LEVELS = ("bust", "underbust", "waist", "hip")

_BODY_FRAC: dict[str, dict[str, float]] = {
    "female": {"bust": 0.26, "underbust": 0.46, "waist": 0.60, "hip": 0.90},
    "male": {"bust": 0.30, "underbust": 0.50, "waist": 0.64, "hip": 0.92},
}
_BUILD_FRAC_TWEAK: dict[str, dict[str, float]] = {
    "slim": {"bust": -0.02, "waist": -0.02, "hip": -0.04},
    "curvy": {"bust": -0.02, "waist": 0.02, "hip": -0.06},
}
_DEPTH_RATIO: dict[str, dict[str, float]] = {
    "female": {"bust": 0.74, "underbust": 0.70, "waist": 0.66, "hip": 0.72},
    "male": {"bust": 0.68, "underbust": 0.66, "waist": 0.62, "hip": 0.70},
}
_HIP_ABOVE_WAIST = {"female": 1.05, "male": 1.03}


@dataclass
class BodyProfile:
    sex: str = "female"  # female | male
    build: str = "average"  # slim | average | curvy
    clothing: str = "auto"  # auto | dsv_vest | fitted | loose_top | loose_dress

    def bmi(self, height_cm: float | None, weight_kg: float | None) -> float | None:
        if not height_cm or not weight_kg or height_cm <= 0:
            return None
        return weight_kg / (height_cm / 100.0) ** 2


@dataclass
class CaptureHints:
    """Lightweight capture metadata for clothing auto-detect."""

    has_dsv_aruco: bool = False
    magenta_band_count: int = 0
    mask_bottom_px: int = 0
    pose: dict | None = None


def torso_fracs(profile: BodyProfile) -> dict[str, float]:
    sex = profile.sex if profile.sex in _BODY_FRAC else "female"
    fracs = dict(_BODY_FRAC[sex])
    for k, delta in _BUILD_FRAC_TWEAK.get(profile.build, {}).items():
        if k in fracs:
            fracs[k] = float(np.clip(fracs[k] + delta, 0.08, 0.98))
    return fracs


def depth_ratio(profile: BodyProfile, level: str) -> float:
    sex = profile.sex if profile.sex in _DEPTH_RATIO else "female"
    base = _DEPTH_RATIO[sex].get(level, 0.68)
    if profile.build == "slim":
        return base * 0.96
    if profile.build == "curvy" and level in ("bust", "hip"):
        return min(base * 1.06, 0.82)
    return base


def detect_clothing(profile: BodyProfile, hints: CaptureHints, samples: list[SliceSample]) -> str:
    if profile.clothing != "auto":
        return profile.clothing
    if hints.has_dsv_aruco or hints.magenta_band_count >= 2:
        return "dsv_vest"
    if hints.pose:
        sh = (hints.pose["l_shoulder"][1] + hints.pose["r_shoulder"][1]) / 2.0
        hip = (hints.pose["l_hip"][1] + hints.pose["r_hip"][1]) / 2.0
        torso = max(1.0, hip - sh)
        skirt_px = max(0, hints.mask_bottom_px - int(hip))
        if skirt_px / torso > 0.35:
            return "loose_dress"
    if not detect_loose_top(samples):
        return "fitted"
    flare = sum(1 for s in samples if s.flare)
    if flare >= max(2, len(samples) // 6):
        return "loose_dress"
    return "loose_top"


def profile_notes(
    profile: BodyProfile,
    clothing: str,
    height_cm: float | None,
    weight_kg: float | None,
) -> list[str]:
    notes = [f"clothing:{clothing}", f"body_profile:{profile.sex}/{profile.build}"]
    bmi = profile.bmi(height_cm, weight_kg)
    if bmi is not None:
        notes.append(f"bmi:{bmi:.1f}")
    return notes


def _pick_level(samples: list[SliceSample], frac: float, mode: str = "mid") -> SliceSample | None:
    usable = [s for s in samples if not s.flare] or samples
    band = [s for s in usable if abs(s.torso_frac - frac) < 0.08] or usable
    if not band:
        return None
    if mode == "max":
        return max(band, key=lambda s: s.girth_cm)
    if mode == "min":
        return min(band, key=lambda s: s.girth_cm)
    return min(band, key=lambda s: abs(s.torso_frac - frac))


def levels_for_profile(
    samples: list[SliceSample],
    profile: BodyProfile,
    clothing: str,
) -> list[ml.LevelMeasure]:
    fracs = torso_fracs(profile)
    loose = clothing in ("loose_top", "loose_dress")
    picks = {
        "bust": _pick_level(samples, fracs["bust"], "max"),
        "underbust": _pick_level(samples, fracs["underbust"], "mid"),
        "waist": _pick_level(samples, fracs["waist"], "min"),
        "hip": _pick_level(samples, fracs["hip"], "max"),
    }
    waist, hip = picks.get("waist"), picks.get("hip")
    hip_girth = hip.girth_cm if hip else None
    if waist and hip and hip.girth_cm < waist.girth_cm:
        hip_girth = round(waist.girth_cm * _HIP_ABOVE_WAIST.get(profile.sex, 1.05), 1)

    levels: list[ml.LevelMeasure] = []
    for name, pick in picks.items():
        if pick is None:
            continue
        girth = hip_girth if name == "hip" and hip_girth and pick is hip else pick.girth_cm
        w_cm, d_cm = pick.width_cm, pick.depth_cm
        if d_cm is None and w_cm:
            d_cm = round(w_cm * depth_ratio(profile, name), 2)
            girth = ml._ellipse_girth_cm(w_cm, d_cm)
        if loose and name == "waist" and picks.get("bust") and girth < picks["bust"].girth_cm * 0.72:
            girth = round(picks["bust"].girth_cm * 0.72, 1)
        levels.append(
            ml.LevelMeasure(
                name=name,
                y_px=pick.y,
                width_cm=round(w_cm, 1),
                depth_cm=round(d_cm, 1) if d_cm else None,
                girth_cm=round(girth, 1),
                confidence=0.72 if not loose else 0.58,
            )
        )
    return levels


def refine_levels_for_profile(
    levels: list[ml.LevelMeasure],
    profile: BodyProfile,
    clothing: str,
) -> list[ml.LevelMeasure]:
    by_name = {lv.name: lv for lv in levels}
    waist, hip, bust, underbust = (
        by_name.get("waist"),
        by_name.get("hip"),
        by_name.get("bust"),
        by_name.get("underbust"),
    )

    def _copy(lv: ml.LevelMeasure, **kw) -> ml.LevelMeasure:
        return ml.LevelMeasure(
            name=kw.get("name", lv.name),
            y_px=kw.get("y_px", lv.y_px),
            width_cm=kw.get("width_cm", lv.width_cm),
            depth_cm=kw.get("depth_cm", lv.depth_cm),
            girth_cm=kw.get("girth_cm", lv.girth_cm),
            confidence=kw.get("confidence", lv.confidence),
        )

    if waist and hip and hip.girth_cm < waist.girth_cm:
        by_name["hip"] = _copy(
            hip,
            girth_cm=round(waist.girth_cm * _HIP_ABOVE_WAIST.get(profile.sex, 1.05), 1),
            confidence=hip.confidence * 0.75,
        )

    if profile.sex == "female" and bust and underbust:
        min_ub = bust.girth_cm * (0.70 if profile.build == "curvy" else 0.74)
        if underbust.girth_cm < min_ub:
            ratio = 0.72 if profile.build == "curvy" else 0.76
            by_name["underbust"] = _copy(
                underbust,
                girth_cm=round(bust.girth_cm * ratio, 1),
                confidence=underbust.confidence * 0.8,
            )

    for name, lv in list(by_name.items()):
        if lv.depth_cm is None and lv.width_cm:
            d = round(lv.width_cm * depth_ratio(profile, name), 2)
            by_name[name] = _copy(lv, depth_cm=d, girth_cm=ml._ellipse_girth_cm(lv.width_cm, d))

    waist = by_name.get("waist")
    hip = by_name.get("hip")
    if clothing == "loose_dress" and waist and hip:
        hip_min = round(waist.girth_cm * 1.08, 1)
        if by_name["hip"].girth_cm < hip_min:
            by_name["hip"] = _copy(by_name["hip"], girth_cm=hip_min, confidence=by_name["hip"].confidence * 0.65)

    order = [by_name[n] for n in GIRTH_LEVELS if n in by_name]
    return order


def estimate_torso_girths_profiled(
    fmask,
    fpose: dict | None,
    fcx: int,
    cm_per_px_front: float,
    side: ml._ProfileView | None,
    cm_per_px_side: float | None,
    profile: BodyProfile | None = None,
    hints: CaptureHints | None = None,
    height_cm: float | None = None,
    weight_kg: float | None = None,
) -> tuple[list[SliceSample], list[ml.LevelMeasure], list[str]]:
    """Slice-sweep with sex/build/clothing-aware body-core switching."""
    prof = profile or BodyProfile()
    cap = hints or CaptureHints(pose=fpose, mask_bottom_px=fmask.shape[0] - 1)

    samples, warnings = scan_torso_slices(
        fmask, fpose, fcx, cm_per_px_front, side, cm_per_px_side,
    )
    clothing = detect_clothing(prof, cap, samples)
    warnings.extend(profile_notes(prof, clothing, height_cm, weight_kg))

    use_body_core = clothing in ("loose_top", "loose_dress") or (
        clothing == "auto" and prof.sex == "female" and detect_loose_top(samples)
    )

    if clothing == "dsv_vest":
        _, levels, w2 = estimate_torso_girths(
            fmask, fpose, fcx, cm_per_px_front, side, cm_per_px_side,
        )
        warnings.extend(w2)
        warnings.append("body_profile:dsv_vest_path")
        return samples, levels, warnings

    if use_body_core and fpose:
        side_pose = side.pose if side else None
        side_top = side.top if side else 0
        side_stat = max(1, (side.bottom - side.top)) if side else 1
        apply_body_core(
            samples, fmask, fcx, fpose, side, side_pose,
            side_top, side_stat, cm_per_px_front, True,
        )
        levels = levels_for_profile(samples, prof, clothing)
        warnings.append(f"body_profile:body_core_{clothing}")
    else:
        _, levels, w2 = estimate_torso_girths(
            fmask, fpose, fcx, cm_per_px_front, side, cm_per_px_side,
        )
        warnings.extend(w2)
        warnings.append("body_profile:fitted_silhouette")

    if clothing != "dsv_vest":
        levels = refine_levels_for_profile(levels, prof, clothing)

    return samples, levels, warnings
