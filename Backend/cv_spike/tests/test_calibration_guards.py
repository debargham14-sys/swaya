"""Sanity checks for global calibration training/apply."""

from pipeline.measure.calibration import (
    CalibrationProfile,
    fit_profile,
    girths_are_plausible,
    profile_is_sane,
)


def test_rejects_blowup_raw_girths():
    assert not girths_are_plausible({"bust": 225.0, "waist": 195.0})


def test_accepts_normal_girths():
    assert girths_are_plausible({"bust": 88.0, "waist": 72.0, "hip": 96.0})


def test_rejects_extreme_affine_from_dress_scan():
    raw = {"bust": 225.0, "waist": 195.0, "hip": 210.0}
    tape = {"bust": 86.0, "waist": 72.0, "hip": 98.0}
    prof = fit_profile(tape, raw, name="bad")
    assert not profile_is_sane(prof)


def test_accepts_mild_correction_profile():
    raw = {"bust": 92.0, "waist": 74.0, "hip": 100.0}
    tape = {"bust": 88.0, "waist": 72.0, "hip": 96.0}
    prof = fit_profile(tape, raw, name="ok")
    assert profile_is_sane(prof)
    assert isinstance(prof, CalibrationProfile)
