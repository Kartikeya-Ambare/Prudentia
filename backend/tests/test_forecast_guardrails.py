import math

import numpy as np
import pandas as pd
import pytest

from backend.forecasting import forecast_guardrails as guardrails
from backend.forecasting import forecaster


def _prices_with_cagr(cagr: float, years: float = 5.0, start: float = 100.0) -> pd.Series:
    """A deterministic price series whose realized CAGR over `years` is
    exactly `cagr` — lets historical-CAGR assertions be exact, not
    seed-dependent."""
    n = int(round(years * guardrails.TRADING_DAYS_PER_YEAR))
    t = np.arange(n + 1)
    prices = start * (1.0 + cagr) ** (t / guardrails.TRADING_DAYS_PER_YEAR)
    dates = pd.date_range("2018-01-01", periods=n + 1, freq="D")
    return pd.Series(prices, index=dates)


def _log_returns(prices: pd.Series) -> np.ndarray:
    return np.diff(np.log(prices.values))


def _run(raw_mu, sigma_annual, prices, horizon_years=5, is_fallback_method=False, config=None, log_returns=None):
    if log_returns is None:
        log_returns = _log_returns(prices)
    return guardrails.run_guardrails(
        raw_mu=raw_mu, sigma_annual=sigma_annual, raw_price_series=prices, clean_prices=prices,
        log_returns=log_returns, horizon_years=horizon_years, is_fallback_method=is_fallback_method,
        config=config or {},
    )


# 1. Normal forecast -----------------------------------------------------

def test_normal_forecast_is_not_flagged_and_confidence_stays_high():
    prices = _prices_with_cagr(0.12)
    result = _run(raw_mu=0.12, sigma_annual=0.20, prices=prices)
    assert "EXTREME_GROWTH" not in result.flags
    assert "HIGH_GROWTH" not in result.flags
    assert result.guarded_mu == pytest.approx(result.raw_mu, abs=1e-9)
    assert result.confidence_score >= 70


# 2. Extreme positive forecast -------------------------------------------

def test_extreme_positive_forecast_is_flagged_and_shrunk():
    prices = _prices_with_cagr(0.12)  # unremarkable history
    result = _run(raw_mu=0.70, sigma_annual=0.25, prices=prices)
    assert "EXTREME_GROWTH" in result.flags
    assert result.confidence_score < 100
    assert result.guarded_cagr_pct < result.raw_cagr_pct
    assert result.guarded_cagr_pct <= 55.0  # soft cap pulled it well below the raw 70%


# 3. Extreme negative forecast -------------------------------------------

def test_extreme_negative_forecast_is_flagged():
    prices = _prices_with_cagr(0.05)
    result = _run(raw_mu=-0.35, sigma_annual=0.30, prices=prices)
    assert "EXTREME_DOWNSIDE" in result.flags
    assert result.confidence_score < 100
    assert result.guarded_cagr_pct > result.raw_cagr_pct  # shrunk back up toward the negative cap


# 4. Historical comparison — forecast far above history -----------------

def test_forecast_significantly_above_history_is_flagged():
    prices = _prices_with_cagr(0.12)
    result = _run(raw_mu=0.65, sigma_annual=0.25, prices=prices)
    assert result.historical_cagr_pct == pytest.approx(12.0, abs=0.5)
    assert "FORECAST_SIGNIFICANTLY_ABOVE_HISTORY" in result.flags


# 5. Historical comparison — forecast close to history -------------------

def test_forecast_close_to_history_is_not_flagged():
    prices = _prices_with_cagr(0.12)
    result = _run(raw_mu=0.15, sigma_annual=0.20, prices=prices)
    assert "FORECAST_SIGNIFICANTLY_ABOVE_HISTORY" not in result.flags
    assert "FORECAST_SIGNIFICANTLY_BELOW_HISTORY" not in result.flags


# 6. Regime shift ----------------------------------------------------------

def test_regime_shift_is_detected():
    rng = np.random.default_rng(7)
    historical = rng.normal(0.0003, 0.005, 100)
    recent = rng.normal(0.0003, 0.0125, 252)  # 2.5x the historical vol
    log_returns = np.concatenate([historical, recent])
    prices = pd.Series(100 * np.exp(np.cumsum(np.concatenate([[0.0], log_returns]))))

    result = _run(raw_mu=0.10, sigma_annual=0.20, prices=prices, log_returns=log_returns)
    assert "REGIME_SHIFT" in result.flags
    assert result.metadata["regime"]["flagged"] is True

    calm_result = _run(raw_mu=0.10, sigma_annual=0.20, prices=prices,
                        log_returns=rng.normal(0.0003, 0.005, 352))
    assert calm_result.confidence_score >= result.confidence_score


# 7. Insufficient history --------------------------------------------------

def test_insufficient_history_warns_without_crashing():
    prices = _prices_with_cagr(0.10, years=0.1)  # ~25 trading days
    result = _run(raw_mu=0.10, sigma_annual=0.20, prices=prices, is_fallback_method=True)
    assert "INSUFFICIENT_HISTORY" in result.flags
    assert math.isfinite(result.guarded_mu)
    assert result.confidence_score < 100


# 8. NaN / Inf inputs -------------------------------------------------------

def test_nan_and_inf_inputs_are_sanitized_without_crashing():
    prices = _prices_with_cagr(0.10)
    result = _run(raw_mu=float("nan"), sigma_annual=float("inf"), prices=prices)
    assert math.isfinite(result.raw_mu)
    assert math.isfinite(result.guarded_mu)
    assert math.isfinite(result.sigma_annual)
    assert "NONFINITE_INPUT_SANITIZED" in result.flags


# 9. Scenario calculation ---------------------------------------------------

def test_scenarios_are_ordered_bear_base_bull():
    prices = _prices_with_cagr(0.12)
    result = _run(raw_mu=0.15, sigma_annual=0.25, prices=prices)
    bear = result.scenarios["bear"]["terminal_price"]
    base = result.scenarios["base"]["terminal_price"]
    bull = result.scenarios["bull"]["terminal_price"]
    assert bear < base < bull


# 2b. Terminal-multiple hard cap (projected price must not exceed Nx) -------

def test_guarded_terminal_price_never_exceeds_configured_multiple():
    prices = _prices_with_cagr(0.12)
    horizon = 5
    sigma = 0.30
    result = _run(raw_mu=0.80, sigma_annual=sigma, prices=prices, horizon_years=horizon)
    assert "TERMINAL_PRICE_CAP_APPLIED" in result.flags
    assert result.terminal_cap_applied is True
    # the effective cap is volatility-scaled (see effective_terminal_max_multiple),
    # not the flat config value, by design -- that's exactly what lets a
    # genuinely volatile instrument keep more upside than a calm one.
    effective_multiple = guardrails.effective_terminal_max_multiple(sigma, {})
    assert effective_multiple > guardrails.DEFAULTS["terminal_cap"]["max_multiple_of_investment"]
    assert result.guarded_terminal_price <= result.current_price * effective_multiple * 1.0001
    # the bull scenario tail is itself a "projected price" and must respect
    # the same ceiling
    assert result.scenarios["bull"]["terminal_price"] <= result.current_price * effective_multiple * 1.0001
    assert result.confidence_score < 100


def test_terminal_cap_is_wider_for_more_volatile_instruments():
    prices = _prices_with_cagr(0.12)
    calm = _run(raw_mu=0.80, sigma_annual=0.15, prices=prices, horizon_years=5)
    volatile = _run(raw_mu=0.80, sigma_annual=0.55, prices=prices, horizon_years=5)
    # Same raw forecast, same history -- the more volatile instrument should
    # be allowed to keep more of its upside, not be squashed to the same
    # ceiling as the calm one (that flattening is what broke the risk
    # thermometer's return ordering).
    assert volatile.guarded_cagr_pct > calm.guarded_cagr_pct
    assert volatile.guarded_terminal_price > calm.guarded_terminal_price


def test_mild_forecast_is_not_terminal_capped():
    prices = _prices_with_cagr(0.12)
    result = _run(raw_mu=0.10, sigma_annual=0.20, prices=prices, horizon_years=5)
    assert "TERMINAL_PRICE_CAP_APPLIED" not in result.flags
    assert result.terminal_cap_applied is False


def test_terminal_cap_can_be_disabled_via_config():
    prices = _prices_with_cagr(0.12)
    config = {"terminal_cap": {"enabled": False}}
    result = _run(raw_mu=0.80, sigma_annual=0.30, prices=prices, horizon_years=5, config=config)
    assert "TERMINAL_PRICE_CAP_APPLIED" not in result.flags
    # soft cap still applies even with the terminal cap off
    assert result.guarded_cagr_pct < result.raw_cagr_pct


# 9b. Scenario band is capped for a volatile + aggressive forecast ----------

def test_scenario_bull_tail_is_capped_for_volatile_stock():
    prices = _prices_with_cagr(0.10)
    # A high raw mu + high sigma would otherwise compound sigma*sqrt(5) into
    # a many-times bull price even after the base mu is soft-capped.
    result = _run(raw_mu=0.80, sigma_annual=0.55, prices=prices)
    assert "SCENARIO_CAPPED" in result.flags
    max_cagr_pct = guardrails.DEFAULTS["scenario"]["max_cagr_pct"]
    assert result.scenarios["bull"]["cagr_pct"] <= max_cagr_pct + 1e-6
    assert result.scenarios["bear"]["cagr_pct"] <= result.scenarios["base"]["cagr_pct"] <= result.scenarios["bull"]["cagr_pct"]


# 10. Mathematical consistency ----------------------------------------------

def test_terminal_price_matches_compounding_formula():
    prices = _prices_with_cagr(0.10)
    horizon = 5
    result = _run(raw_mu=0.10, sigma_annual=0.20, prices=prices, horizon_years=horizon)
    expected_terminal = result.current_price * (1.0 + result.guarded_mu) ** horizon
    assert result.guarded_terminal_price == pytest.approx(expected_terminal, rel=1e-9)
    # the scenario band's "base" case is the same identity in log-price space
    assert result.scenarios["base"]["terminal_price"] == pytest.approx(expected_terminal, rel=1e-3)


# 11. Cache invalidation ------------------------------------------------------

@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(forecaster, "FORECAST_CACHE_DIR", tmp_path)
    return tmp_path


def _synthetic_prices(n=300, drift=0.0004, vol=0.015, seed=42) -> pd.Series:
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(drift, vol, n)
    prices = 100 * np.exp(np.cumsum(log_returns))
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    return pd.Series(prices, index=dates)


def test_old_unguarded_cache_entry_is_invalidated(isolated_cache):
    import json
    from datetime import datetime

    series = _synthetic_prices()
    old_payload = {
        "mu": 0.9, "sigma": 0.2, "n_obs": 250, "method": "transformer",
        "computed_at": datetime.now().isoformat(),
        # no "guardrail_version" -- simulates a cache file written before
        # the guardrail layer existed.
    }
    cache_path = forecaster._cache_path("LEGACY.NS")
    cache_path.write_text(json.dumps(old_payload), encoding="utf-8")

    result = forecaster.forecast_ticker("LEGACY.NS", series, force_refresh=False)
    assert "guardrail_status" in result
    assert result["mu"] != 0.9  # the stale unguarded value was not trusted


# 12. Backward compatibility --------------------------------------------------

def test_forecast_ticker_still_returns_legacy_keys(isolated_cache):
    series = _synthetic_prices()
    result = forecaster.forecast_ticker("COMPAT.NS", series, force_refresh=True)
    assert "mu" in result and math.isfinite(result["mu"])
    assert "sigma" in result and result["sigma"] > 0
    assert "n_obs" in result
    assert "raw_mu" in result and math.isfinite(result["raw_mu"])
