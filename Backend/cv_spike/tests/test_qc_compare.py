"""Stage-5 comparison tests: tolerance tiers + Pass/Fail/NeedsReview logic."""

from __future__ import annotations

from pipeline.qc.compare import FAIL, NEEDS_REVIEW, PASS, compare_dimensions
from pipeline.qc.dimensions import DimensionSet, Measurement
from pipeline.qc.spec import OrderSpec, tolerance_mm


def test_tolerance_tiers():
    assert tolerance_mm("bust", "couture") == 3.0
    assert tolerance_mm("bust", "bespoke") == 5.0
    assert tolerance_mm("bust", "express") == 8.0
    assert tolerance_mm("shoulder_width", "express") == 3.0
    # unknown dimension falls back to per-tier default
    assert tolerance_mm("mystery_dim", "couture") == 2.0
    assert tolerance_mm("mystery_dim", "express") == 5.0


def _dims(values: dict[str, float], conf: float = 0.8) -> DimensionSet:
    ds = DimensionSet()
    from pipeline.qc.dimensions import DIMENSION_KINDS

    for name, v in values.items():
        kind = DIMENSION_KINDS.get(name, "linear")
        ds.measurements[name] = Measurement(name, v, kind, conf)
    return ds


def test_pass_within_tolerance():
    spec = OrderSpec(order_id="t1", tier="bespoke", target_dims_mm={"bust": 860})
    res = compare_dimensions(_dims({"bust": 863}), spec)
    assert res[0].status == PASS
    assert res[0].deviation_mm == 3.0


def test_fail_outside_tolerance():
    spec = OrderSpec(order_id="t2", tier="bespoke", target_dims_mm={"shoulder_width": 380})
    res = compare_dimensions(_dims({"shoulder_width": 386}), spec)
    assert res[0].status == FAIL


def test_tier_changes_verdict():
    # 6 mm bust deviation: fail at couture/bespoke, pass at express.
    target = {"bust": 860}
    measured = {"bust": 866}
    couture = compare_dimensions(_dims(measured), OrderSpec("c", tier="couture", target_dims_mm=target))
    express = compare_dimensions(_dims(measured), OrderSpec("e", tier="express", target_dims_mm=target))
    assert couture[0].status == FAIL
    assert express[0].status == PASS


def test_low_confidence_is_needs_review():
    spec = OrderSpec(order_id="t3", tier="bespoke", target_dims_mm={"bust": 860})
    res = compare_dimensions(_dims({"bust": 860}, conf=0.1), spec)
    assert res[0].status == NEEDS_REVIEW


def test_unmeasured_dimension_is_needs_review():
    spec = OrderSpec(order_id="t4", tier="bespoke", target_dims_mm={"waist": 700})
    res = compare_dimensions(_dims({}), spec)  # waist not measured
    assert res[0].status == NEEDS_REVIEW
    assert res[0].measured_mm is None
