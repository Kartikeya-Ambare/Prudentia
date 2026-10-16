import pytest

from backend.forecasting.fundamentals_formatter import bucket_projection, instrument_projection


def test_instrument_projection_compounds_correctly():
    proj = instrument_projection("TCS.NS", present_value=42000, mu_post_tax=0.12, horizon_years=5)
    assert proj.present_value == 42000
    assert proj.projected_value == pytest.approx(42000 * 1.12 ** 5, rel=1e-9)
    assert proj.projected_return_pct == pytest.approx(12.0)


def test_bucket_projection_aggregates_present_and_projected():
    a = instrument_projection("A", 10000, 0.10, 5)
    b = instrument_projection("B", 20000, 0.20, 5)
    bucket = bucket_projection("Stocks", [a, b], horizon_years=5)
    assert bucket.present_value == 30000
    assert bucket.projected_value == pytest.approx(a.projected_value + b.projected_value)
    # implied annual return must be between the two instrument rates
    assert 10.0 < bucket.projected_return_pct < 20.0


def test_bucket_projection_handles_zero_present_value():
    bucket = bucket_projection("Empty", [], horizon_years=5)
    assert bucket.present_value == 0
    assert bucket.projected_return_pct == 0.0
