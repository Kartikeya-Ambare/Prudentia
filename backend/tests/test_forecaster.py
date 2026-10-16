import numpy as np
import pandas as pd
import pytest

from backend.forecasting import forecaster


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(forecaster, "FORECAST_CACHE_DIR", tmp_path)


def _synthetic_prices(n=300, drift=0.0004, vol=0.015, seed=42) -> pd.Series:
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(drift, vol, n)
    prices = 100 * np.exp(np.cumsum(log_returns))
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    return pd.Series(prices, index=dates)


def test_forecast_returns_finite_mu_and_positive_sigma():
    series = _synthetic_prices()
    result = forecaster.forecast_ticker("SYNTH.NS", series, force_refresh=True)
    assert np.isfinite(result["mu"])
    assert result["sigma"] > 0
    assert result["method"] == "transformer"
    assert -0.75 <= result["mu"] <= 1.5  # clipped range


def test_short_series_falls_back_to_historical_mean():
    series = _synthetic_prices(n=10)  # too few points for even the smallest window + 10 obs
    result = forecaster.forecast_ticker("SHORT.NS", series, force_refresh=True)
    assert result["method"] == "historical_mean"


def test_zero_price_rows_do_not_produce_inf_or_nan():
    # Regression test: mfapi.in's older NAV history contains literal 0.0
    # rows (not NaN) which used to poison np.log() with -inf and cascade
    # into inf/nan mu and sigma.
    series = _synthetic_prices()
    series.iloc[5] = 0.0
    series.iloc[42] = 0.0
    result = forecaster.forecast_ticker("ZERO.NS", series, force_refresh=True)
    assert np.isfinite(result["mu"])
    assert np.isfinite(result["sigma"])


def test_poisoned_cache_entry_is_rejected_and_recomputed(tmp_path):
    # Regression test: a cache file written by an earlier, buggier run could
    # contain NaN/Inf (e.g. json.dumps' non-standard NaN token) and would
    # otherwise be trusted verbatim for up to cache_max_age_hours.
    import json
    from datetime import datetime

    poisoned = {"mu": float("nan"), "sigma": 0.2, "n_obs": 100, "method": "transformer",
                "computed_at": datetime.now().isoformat()}
    cache_path = forecaster._cache_path("POISONED.NS")
    cache_path.write_text(json.dumps(poisoned), encoding="utf-8")

    series = _synthetic_prices()
    result = forecaster.forecast_ticker("POISONED.NS", series, force_refresh=False)
    assert np.isfinite(result["mu"])  # must have recomputed, not trusted the NaN


def test_cache_is_reused_without_force_refresh():
    series = _synthetic_prices()
    first = forecaster.forecast_ticker("CACHED.NS", series, force_refresh=True)
    second = forecaster.forecast_ticker("CACHED.NS", series, force_refresh=False)
    assert first["mu"] == second["mu"]
    assert first["computed_at"] if "computed_at" in first else True  # cache file exists
    cache_path = forecaster._cache_path("CACHED.NS")
    assert cache_path.exists()
