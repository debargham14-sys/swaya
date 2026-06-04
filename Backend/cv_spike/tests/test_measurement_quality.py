from pipeline.measure.measure_engine import EngineResult
from pipeline.measure.measurement_quality import apply_quality_gate


def test_suppresses_dress_blowup():
    r = EngineResult(
        backend="photo",
        height_cm=163,
        weight_kg=55,
        bmi=20.0,
        girths_cm={"bust": 229.6, "waist": 223.4},
        confidence=0.7,
        warnings=["pose_not_detected_slice_sweep_degraded"],
    )
    out = apply_quality_gate(r)
    assert out.girths_cm == {}
    assert "measurements_unreliable" in " ".join(out.warnings)


def test_keeps_plausible_when_only_side_grabcut_fallback():
    r = EngineResult(
        backend="photo",
        height_cm=163,
        weight_kg=55,
        bmi=20.0,
        girths_cm={"bust": 89.4, "waist": 64.8, "hip": 64.8},
        confidence=0.72,
        warnings=[
            "side:segmentation_fallback_grabcut",
            "approximate: fitted clothing improves accuracy",
        ],
    )
    out = apply_quality_gate(r)
    assert out.girths_cm["bust"] == 89.4
