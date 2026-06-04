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
    assert out.girths_raw_cm["bust"] == 229.6
    assert "measurements_unreliable" in " ".join(out.warnings)
