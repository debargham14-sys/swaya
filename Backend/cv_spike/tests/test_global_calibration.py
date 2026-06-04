"""Global calibration learns from ground-truth errors."""

from pipeline.measure.calibration import apply_girth_calibration, fit_profile
from pipeline.measure.measure_engine import EngineResult


def test_apply_to_engine_result_without_profile():
    from api.services.calibration_service import apply_to_engine_result

    r = EngineResult(
        backend="photo",
        height_cm=170,
        weight_kg=70,
        bmi=24.0,
        girths_cm={"bust": 100.0, "waist": 80.0},
    )
    out = apply_to_engine_result(r)
    assert out.girths_cm["bust"] == 100.0
    assert out.girths_raw_cm.get("bust") == 100.0


def test_affine_fit_reduces_error_on_next_apply():
    raw = {"bust": 90.0, "waist": 70.0, "hip": 95.0}
    tape = {"bust": 100.0, "waist": 78.0, "hip": 102.0}
    prof = fit_profile(tape, raw, name="global")
    cal = apply_girth_calibration(raw, prof)
    for k in tape:
        assert abs(cal[k] - tape[k]) < 2.0
