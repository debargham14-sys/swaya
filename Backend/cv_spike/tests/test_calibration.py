"""Tape calibration affine fit."""

from pipeline.calibration import (
    apply_girth_calibration,
    fit_affine_girth,
    fit_profile,
    parse_tape_spec,
)


def test_parse_tape_inches():
    a = parse_tape_spec("chest=44,waist=38", unit="in")
    assert abs(a["bust"] - 44 * 2.54) < 0.1
    assert abs(a["waist"] - 38 * 2.54) < 0.1


def test_affine_two_anchors_matches_manual():
    raw = {"bust": 141.5, "underbust": 126.1, "waist": 113.3, "hip": 104.4}
    anchors = parse_tape_spec("bust=44,waist=38", unit="in")
    scale, offset = fit_affine_girth(anchors, raw)
    prof = fit_profile(anchors, raw, name="test")
    cal = apply_girth_calibration(raw, prof)
    assert abs(cal["bust"] - anchors["bust"]) < 0.5
    assert abs(cal["waist"] - anchors["waist"]) < 0.5
    # hip extrapolated ~36-38 in
    assert 90 < cal["hip"] < 100
