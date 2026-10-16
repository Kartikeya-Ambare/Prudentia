"""Guardrail layer for the long-horizon forecast produced by forecaster.py's
Transformer.

This module does not change what the Transformer predicts. It inspects the
annualized expected return (`raw_mu`) the Transformer-derived pipeline
already produced, compares the implied multi-year trajectory against the
instrument's own history, and produces a *guarded* return plus a bundle of
diagnostics (flags/warnings/confidence/scenarios) that forecaster.py attaches
to its result. None of this proves the guarded number is "correct" — it only
prevents an implausible model output from silently reaching the optimizer
unexamined.

Units / semantics (traced from the rest of the pipeline, not assumed):
  - `backend/forecasting/fundamentals_formatter.py` turns `mu` into a value
    projection via ``present_value * (1 + mu) ** horizon_years``.
  - `backend/forecasting/black_litterman_optimizer.py` feeds `mu` straight
    into `BlackLittermanModel(absolute_views=...)`, compared against
    `pypfopt.expected_returns.mean_historical_return`, which is itself a
    simple (non-log) annualized return.
  Both call sites treat `mu` as a plain annualized *simple* return factor,
  even though forecaster.py derives it from log returns internally. This
  module follows that same convention throughout so a `guarded_mu` it hands
  back behaves identically to the `raw_mu` it replaces:

      CAGR (%)        = mu * 100
      terminal_price  = current_price * (1 + mu) ** horizon_years

  `sigma` (sigma_annual) is left as forecaster.py already computes it: the
  annualized standard deviation of *log* returns. The bear/base/bull scenario
  band (see `build_scenarios`) works in log-price space, where that sigma's
  units are native, using the exact identity
  ``log(P_T) = log(P0) + horizon_years * log(1 + mu)`` -- so the scenario
  band's "base" case lands exactly on the same terminal price as
  `guarded_terminal_price`, not an approximation of it.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252

# Fallback thresholds used whenever `config.yaml`'s `forecaster.guardrails`
# section (or a test's stand-in config) omits a key. Keeps every threshold
# overridable without requiring a fully-populated config for simple tests.
DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "version": 1,
    "cagr": {
        "high_positive_pct": 20.0,
        "extreme_positive_pct": 35.0,
        "high_negative_pct": -15.0,
        "extreme_negative_pct": -25.0,
    },
    "historical": {
        "comparison_enabled": True,
        "deviation_multiplier": 2.5,
        "minimum_difference_pct": 15.0,
        "min_years_for_comparison": 1.0,
    },
    "regime": {
        "enabled": True,
        "recent_window_days": 252,
        "volatility_ratio_high": 2.0,
        "volatility_ratio_low": 0.5,
    },
    "volatility": {
        "high_annual_pct": 45.0,
    },
    "drawdown": {
        "high_drawdown_pct": -40.0,
    },
    "confidence": {
        "base_score": 100.0,
        "penalty_extreme_cagr": 25.0,
        "penalty_high_cagr": 10.0,
        "penalty_history_deviation": 15.0,
        "penalty_regime_shift": 15.0,
        "penalty_high_volatility": 10.0,
        "penalty_insufficient_history": 30.0,
        "penalty_data_quality": 40.0,
        "penalty_drawdown_risk": 10.0,
        "penalty_terminal_cap": 10.0,
    },
    "scenario": {
        "enabled": True,
        "bear_sigma_multiplier": 0.75,
        "bull_sigma_multiplier": 0.75,
        # Outer bound on the bear/bull tails' own implied CAGR, independent
        # of (and wider than) the base-case soft cap below — see
        # `build_scenarios`'s docstring for why this exists.
        "max_cagr_pct": 45.0,
        "min_cagr_pct": -35.0,
    },
    "soft_cap": {
        "enabled": True,
        "positive_cagr_pct": 22.0,
        "negative_cagr_pct": -18.0,
        "shrinkage_factor": 0.3,
        # Scales the positive ceiling up for instruments more volatile than
        # `baseline_volatility_pct`, so a genuinely volatile ("aggressive")
        # pick isn't squashed to the same cap as a sleepy one — see the
        # long comment above `_volatility_scaled_bound`.
        "volatility_scaling_enabled": True,
        "baseline_volatility_pct": 20.0,
        "volatility_scaling_per_10pct": 2.5,
        "absolute_max_positive_cagr_pct": 40.0,
    },
    "data_quality": {
        "min_observations": 30,
        "extreme_daily_log_return": 0.5,
    },
    # User-specified hard rule: the projected price/value must never exceed
    # `max_multiple_of_investment`x the current price/invested amount over
    # the forecast horizon, regardless of what the soft cap alone would
    # allow. Unlike `soft_cap`, this clamps (no shrinkage) and only bounds
    # the upside.
    "terminal_cap": {
        "enabled": True,
        "max_multiple_of_investment": 2.5,
        # Same volatility scaling as soft_cap, in multiple-space rather than
        # CAGR-space — see the long comment above `_volatility_scaled_bound`.
        "volatility_scaling_enabled": True,
        "baseline_volatility_pct": 20.0,
        "volatility_scaling_per_10pct": 0.3,
        "absolute_max_multiple": 4.0,
    },
}


def _get(cfg: Any, *keys: str) -> Any:
    node = cfg
    for key in keys:
        if node is None:
            return None
        getter = getattr(node, "get", None)
        if getter is None:
            return None
        node = getter(key)
    return node


def _cfg(cfg: Any, *keys: str) -> Any:
    """Look up `keys` in `cfg` (a ConfigNode or plain/partial dict); fall
    back to DEFAULTS when `cfg` doesn't have the key at all."""
    value = _get(cfg, *keys)
    if value is not None:
        return value
    node: Any = DEFAULTS
    for key in keys:
        node = node[key]
    return node


def _finite(x: Any) -> bool:
    try:
        return math.isfinite(x)
    except (TypeError, ValueError):
        return False


@dataclass
class ForecastGuardrailResult:
    raw_mu: float
    guarded_mu: float
    sigma_annual: float
    current_price: float
    raw_terminal_price: float
    guarded_terminal_price: float
    raw_cagr_pct: float
    guarded_cagr_pct: float
    historical_cagr_pct: float | None
    historical_cagr_years: float | None
    historical_volatility_pct: float
    historical_max_drawdown_pct: float | None
    confidence_score: float
    confidence_status: str
    guardrail_status: str
    data_quality_status: str
    soft_cap_applied: bool
    terminal_cap_applied: bool
    flags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trajectory: list[dict] = field(default_factory=list)
    scenarios: dict[str, dict] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Guardrail #1 — data quality
# ---------------------------------------------------------------------------

def check_data_quality(
    raw_series: pd.Series | None, clean_prices: pd.Series | None, log_returns: np.ndarray | None, cfg: Any,
) -> tuple[str, list[str], list[str]]:
    flags: list[str] = []
    warnings: list[str] = []

    if raw_series is None or raw_series.empty:
        flags.append("EMPTY_SERIES")
        warnings.append("Price history is empty; cannot forecast reliably.")
        return "INVALID", flags, warnings

    if raw_series.isna().all():
        flags.append("ALL_NAN")
        warnings.append("Price history contains only missing values.")
        return "INVALID", flags, warnings

    n_missing = int(raw_series.isna().sum())
    if n_missing > 0 and len(raw_series) > 0 and (n_missing / len(raw_series)) > 0.1:
        flags.append("EXCESSIVE_MISSING_DATA")
        warnings.append(f"{n_missing / len(raw_series):.0%} of the price history is missing.")

    if (raw_series.dropna() <= 0).any():
        flags.append("NON_POSITIVE_PRICES")
        warnings.append("Price history contains zero/negative values; those rows were dropped before forecasting.")

    if raw_series.index.has_duplicates:
        flags.append("DUPLICATE_DATES")
        warnings.append("Price history contains duplicate dates.")

    if not raw_series.index.is_monotonic_increasing:
        flags.append("NON_MONOTONIC_INDEX")
        warnings.append("Price history dates are not sorted in ascending order.")

    min_obs = int(_cfg(cfg, "data_quality", "min_observations"))
    n_clean = 0 if clean_prices is None else len(clean_prices)
    if n_clean < min_obs:
        flags.append("INSUFFICIENT_HISTORY")
        warnings.append(
            f"Only {n_clean} usable price observations (< {min_obs}); forecast reliability is reduced."
        )

    if log_returns is not None and len(log_returns):
        extreme_thresh = float(_cfg(cfg, "data_quality", "extreme_daily_log_return"))
        finite_returns = log_returns[np.isfinite(log_returns)]
        if len(finite_returns) and np.any(np.abs(finite_returns) > extreme_thresh):
            flags.append("EXTREME_DAILY_MOVE")
            warnings.append("Price history contains at least one implausibly large single-day move.")
        if len(finite_returns) != len(log_returns):
            flags.append("NON_FINITE_RETURNS")
            warnings.append("Price history produced non-finite daily returns; those points were ignored.")

    if {"NON_POSITIVE_PRICES", "EXCESSIVE_MISSING_DATA", "DUPLICATE_DATES", "NON_FINITE_RETURNS"} & set(flags):
        status = "DEGRADED"
    elif "INSUFFICIENT_HISTORY" in flags:
        status = "INSUFFICIENT"
    else:
        status = "OK"
    return status, flags, warnings


# ---------------------------------------------------------------------------
# Guardrail #2/#4 — CAGR classification + historical comparison
# ---------------------------------------------------------------------------

def classify_cagr(cagr_pct: float, cfg: Any) -> str:
    extreme_pos = float(_cfg(cfg, "cagr", "extreme_positive_pct"))
    high_pos = float(_cfg(cfg, "cagr", "high_positive_pct"))
    extreme_neg = float(_cfg(cfg, "cagr", "extreme_negative_pct"))
    high_neg = float(_cfg(cfg, "cagr", "high_negative_pct"))
    if cagr_pct > extreme_pos:
        return "EXTREME_GROWTH"
    if cagr_pct > high_pos:
        return "HIGH_GROWTH"
    if cagr_pct < extreme_neg:
        return "EXTREME_DOWNSIDE"
    if cagr_pct < high_neg:
        return "HIGH_DOWNSIDE"
    return "NORMAL_RANGE"


def historical_cagr(clean_prices: pd.Series, years: float) -> float | None:
    if clean_prices is None or len(clean_prices) < 2:
        return None
    lookback = min(len(clean_prices) - 1, int(round(years * TRADING_DAYS_PER_YEAR)))
    if lookback <= 0:
        return None
    start_price = float(clean_prices.iloc[-lookback - 1])
    end_price = float(clean_prices.iloc[-1])
    actual_years = lookback / TRADING_DAYS_PER_YEAR
    if start_price <= 0 or not _finite(start_price) or not _finite(end_price) or actual_years <= 0:
        return None
    cagr = (end_price / start_price) ** (1.0 / actual_years) - 1.0
    return cagr if _finite(cagr) else None


def best_historical_cagr(clean_prices: pd.Series) -> tuple[float | None, float | None]:
    """Prefer ~5y of history, then ~3y, then whatever (>=1y) is available."""
    for years in (5.0, 3.0, 1.0):
        cagr = historical_cagr(clean_prices, years)
        if cagr is not None:
            lookback = min(len(clean_prices) - 1, int(round(years * TRADING_DAYS_PER_YEAR)))
            return cagr, lookback / TRADING_DAYS_PER_YEAR
    return None, None


def compare_to_history(forecast_cagr_pct: float, historical_cagr_pct: float | None, cfg: Any) -> tuple[str | None, str | None]:
    if historical_cagr_pct is None or not bool(_cfg(cfg, "historical", "comparison_enabled")):
        return None, None
    diff = forecast_cagr_pct - historical_cagr_pct
    min_diff = float(_cfg(cfg, "historical", "minimum_difference_pct"))
    multiplier = float(_cfg(cfg, "historical", "deviation_multiplier"))
    threshold = max(min_diff, abs(historical_cagr_pct) * (multiplier - 1.0))
    if abs(diff) < threshold:
        return None, None
    if diff > 0:
        return (
            "FORECAST_SIGNIFICANTLY_ABOVE_HISTORY",
            f"Forecast CAGR ({forecast_cagr_pct:.1f}%) is well above the instrument's historical "
            f"CAGR ({historical_cagr_pct:.1f}%).",
        )
    return (
        "FORECAST_SIGNIFICANTLY_BELOW_HISTORY",
        f"Forecast CAGR ({forecast_cagr_pct:.1f}%) is well below the instrument's historical "
        f"CAGR ({historical_cagr_pct:.1f}%).",
    )


# ---------------------------------------------------------------------------
# Guardrail #3 — soft CAGR cap (shrinkage, not a hard clip)
# ---------------------------------------------------------------------------
#
# Both the soft cap and the terminal-multiple cap below scale their *upside*
# bound with the instrument's own historical volatility (never the
# downside). Without this, a single flat ceiling squashes every instrument
# — a sleepy large-cap and a genuinely volatile small-cap alike — down to
# the same number, which erases the very differentiation the risk
# thermometer depends on: the "aggressive" risk band deliberately selects
# higher-volatility instruments (backend/selection/universe_selector.py's
# volatility-band filter), expecting them to carry a higher *potential*
# return; a volatility-blind cap defeats that by capping them identically to
# a conservative pick, which can make a higher-risk allocation end up with a
# *lower* blended expected return than a lower-risk one — exactly backwards.
# Scaling the ceiling by each instrument's own sigma keeps genuinely extreme
# forecasts bounded while preserving that risk/return ordering.

def _volatility_scaled_bound(
    base_bound: float, sigma_annual: float, absolute_max: float, cfg: Any, cfg_section: str,
) -> float:
    if not bool(_cfg(cfg, cfg_section, "volatility_scaling_enabled")):
        return base_bound
    baseline_vol_pct = float(_cfg(cfg, cfg_section, "baseline_volatility_pct"))
    scaling_per_10pct = float(_cfg(cfg, cfg_section, "volatility_scaling_per_10pct"))
    vol_excess_pct = max(0.0, sigma_annual * 100.0 - baseline_vol_pct)
    scaled = base_bound + scaling_per_10pct * (vol_excess_pct / 10.0)
    return min(scaled, absolute_max)


def effective_soft_cap_positive_pct(sigma_annual: float, cfg: Any) -> float:
    base = float(_cfg(cfg, "soft_cap", "positive_cagr_pct"))
    absolute_max = float(_cfg(cfg, "soft_cap", "absolute_max_positive_cagr_pct"))
    return _volatility_scaled_bound(base, sigma_annual, absolute_max, cfg, "soft_cap")


def apply_soft_cap(cagr_pct: float, sigma_annual: float, cfg: Any) -> tuple[float, bool]:
    if not bool(_cfg(cfg, "soft_cap", "enabled")):
        return cagr_pct, False
    pos_cap = effective_soft_cap_positive_pct(sigma_annual, cfg)
    neg_cap = float(_cfg(cfg, "soft_cap", "negative_cagr_pct"))
    shrink = float(_cfg(cfg, "soft_cap", "shrinkage_factor"))
    if cagr_pct > pos_cap:
        return pos_cap + shrink * (cagr_pct - pos_cap), True
    if cagr_pct < neg_cap:
        return neg_cap + shrink * (cagr_pct - neg_cap), True
    return cagr_pct, False


# ---------------------------------------------------------------------------
# Guardrail #3b — hard cap on the terminal multiple of the initial price
# (equivalently, of the initial invested amount — present_value scales the
# same compounding factor as price, so capping the per-share multiple caps
# the rupee multiple identically).
# ---------------------------------------------------------------------------

def max_cagr_pct_for_multiple(max_multiple: float, horizon_years: float) -> float | None:
    """The annualized CAGR (%) at which `(1 + cagr) ** horizon_years`
    exactly equals `max_multiple`. Any CAGR above this would project a
    terminal price/value more than `max_multiple`x the starting one."""
    if max_multiple is None or max_multiple <= 0 or horizon_years is None or horizon_years <= 0:
        return None
    return (max_multiple ** (1.0 / horizon_years) - 1.0) * 100.0


def effective_terminal_max_multiple(sigma_annual: float, cfg: Any) -> float:
    base_multiple = float(_cfg(cfg, "terminal_cap", "max_multiple_of_investment"))
    absolute_max = float(_cfg(cfg, "terminal_cap", "absolute_max_multiple"))
    return _volatility_scaled_bound(base_multiple, sigma_annual, absolute_max, cfg, "terminal_cap")


def apply_terminal_multiple_cap(cagr_pct: float, sigma_annual: float, horizon_years: float, cfg: Any) -> tuple[float, bool]:
    """Hard ceiling (not a shrink — the user-specified rule is an absolute
    "must not exceed", unlike the softer `apply_soft_cap`). Only caps the
    upside; a loss is never "more than Nx the investment" in this sense."""
    if not bool(_cfg(cfg, "terminal_cap", "enabled")):
        return cagr_pct, False
    max_multiple = effective_terminal_max_multiple(sigma_annual, cfg)
    cap_pct = max_cagr_pct_for_multiple(max_multiple, horizon_years)
    if cap_pct is None or cagr_pct <= cap_pct:
        return cagr_pct, False
    return cap_pct, True


# ---------------------------------------------------------------------------
# Guardrail #7 — drawdown context
# ---------------------------------------------------------------------------

def max_drawdown_pct(clean_prices: pd.Series | None) -> float | None:
    if clean_prices is None or len(clean_prices) < 2:
        return None
    running_max = clean_prices.cummax()
    drawdown = (clean_prices - running_max) / running_max
    value = float(drawdown.min())
    return value * 100.0 if _finite(value) else None


# ---------------------------------------------------------------------------
# Guardrail #8 — lightweight regime / distribution-shift check
# ---------------------------------------------------------------------------

def regime_shift(log_returns: np.ndarray | None, cfg: Any) -> dict:
    result: dict[str, Any] = {
        "flagged": False, "recent_volatility_pct": None, "historical_volatility_pct": None, "ratio": None,
    }
    window = int(_cfg(cfg, "regime", "recent_window_days"))
    if log_returns is None or len(log_returns) < window + 30:
        return result
    recent = log_returns[-window:]
    historical = log_returns[:-window]
    if len(historical) < 30:
        return result
    recent_vol = float(np.std(recent)) * math.sqrt(TRADING_DAYS_PER_YEAR)
    hist_vol = float(np.std(historical)) * math.sqrt(TRADING_DAYS_PER_YEAR)
    result["recent_volatility_pct"] = recent_vol * 100.0
    result["historical_volatility_pct"] = hist_vol * 100.0
    if hist_vol <= 1e-9:
        return result
    ratio = recent_vol / hist_vol
    result["ratio"] = ratio
    high = float(_cfg(cfg, "regime", "volatility_ratio_high"))
    low = float(_cfg(cfg, "regime", "volatility_ratio_low"))
    result["flagged"] = ratio > high or ratio < low
    return result


# ---------------------------------------------------------------------------
# Guardrail #6 — year-by-year trajectory
# ---------------------------------------------------------------------------

def build_trajectory(current_price: float, guarded_mu: float, horizon_years: int) -> list[dict]:
    trajectory: list[dict] = []
    prev_price = current_price
    for year in range(0, int(horizon_years) + 1):
        price = current_price * (1.0 + guarded_mu) ** year
        if not _finite(price) or price < 0:
            price = prev_price if _finite(prev_price) else 0.0
        annual_return_pct = ((price / prev_price) - 1.0) * 100 if year > 0 and prev_price > 0 else 0.0
        cumulative_return_pct = ((price / current_price) - 1.0) * 100 if current_price > 0 else 0.0
        trajectory.append({
            "year": year,
            "projected_price": round(price, 4),
            "annual_return_pct": round(annual_return_pct, 4),
            "cumulative_return_pct": round(cumulative_return_pct, 4),
        })
        prev_price = price
    return trajectory


# ---------------------------------------------------------------------------
# Guardrail #9 — bear/base/bull scenario band
# ---------------------------------------------------------------------------

def _safe_exp(log_value: float) -> float:
    clipped = max(min(log_value, 60.0), -60.0)  # exp(60) ~ 1e26, well clear of float64 overflow
    return float(np.exp(clipped))


def _cagr_pct_from_terminal(terminal_price: float, current_price: float, horizon_years: float) -> float:
    if horizon_years <= 0 or current_price <= 0:
        return 0.0
    return ((terminal_price / current_price) ** (1.0 / horizon_years) - 1.0) * 100


def build_scenarios(
    current_price: float, guarded_mu: float, sigma_annual: float, horizon_years: float, cfg: Any,
) -> tuple[dict, bool]:
    """Bear/base/bull terminal prices. The base case reuses the exact same
    `(1 + mu) ** H` compounding as `guarded_terminal_price` (no log round-trip
    drift). The bear/bull tails are built in log-price space, where sigma's
    units are native (`uncertainty = sigma * sqrt(H)`), then — because
    `sigma * sqrt(H)` compounded over a 5-year horizon can imply a many-times
    move even after the base `mu` is already guarded — each tail's *implied
    CAGR* is itself clamped to `scenario.max_cagr_pct` / `min_cagr_pct` before
    being converted back to a price. This is guardrail #9's own soft cap: it
    keeps the tails informative without letting compounding make them
    absurd. `capped` reports whether either tail actually got clamped.
    """
    if not bool(_cfg(cfg, "scenario", "enabled")) or current_price <= 0 or not _finite(current_price):
        return {}, False
    bear_mult = float(_cfg(cfg, "scenario", "bear_sigma_multiplier"))
    bull_mult = float(_cfg(cfg, "scenario", "bull_sigma_multiplier"))
    sigma_safe = sigma_annual if _finite(sigma_annual) and sigma_annual >= 0 else 0.0

    base_cagr_pct = guarded_mu * 100.0
    log_p0 = math.log(current_price)
    mu_log_equiv = math.log1p(max(guarded_mu, -0.999999))
    base_log_price = log_p0 + mu_log_equiv * horizon_years
    uncertainty = sigma_safe * math.sqrt(max(horizon_years, 0.0))

    bear_cagr_raw = _cagr_pct_from_terminal(_safe_exp(base_log_price - bear_mult * uncertainty), current_price, horizon_years)
    bull_cagr_raw = _cagr_pct_from_terminal(_safe_exp(base_log_price + bull_mult * uncertainty), current_price, horizon_years)

    max_cagr = float(_cfg(cfg, "scenario", "max_cagr_pct"))
    min_cagr = float(_cfg(cfg, "scenario", "min_cagr_pct"))
    # The bull tail is itself a "projected price" and must respect the same
    # hard terminal-multiple ceiling as the base case (guardrail #3b) — take
    # whichever of the two upper bounds is tighter.
    terminal_cap_pct = max_cagr_pct_for_multiple(
        effective_terminal_max_multiple(sigma_safe, cfg), horizon_years,
    ) if bool(_cfg(cfg, "terminal_cap", "enabled")) else None
    if terminal_cap_pct is not None:
        max_cagr = min(max_cagr, terminal_cap_pct)
    # The `max(..., base_cagr_pct)` / `min(..., base_cagr_pct)` floors guarantee
    # bear <= base <= bull always holds, even for a misconfigured cap tighter
    # than the (already-guarded) base case.
    bull_cagr = max(min(bull_cagr_raw, max_cagr), base_cagr_pct)
    bear_cagr = min(max(bear_cagr_raw, min_cagr), base_cagr_pct)
    capped = not math.isclose(bull_cagr, bull_cagr_raw, abs_tol=1e-9) or not math.isclose(bear_cagr, bear_cagr_raw, abs_tol=1e-9)

    def _price(cagr_pct: float) -> float:
        return current_price * (1.0 + cagr_pct / 100.0) ** horizon_years

    scenarios = {
        "bear": {"terminal_price": round(_price(bear_cagr), 4), "cagr_pct": round(bear_cagr, 4)},
        "base": {"terminal_price": round(_price(base_cagr_pct), 4), "cagr_pct": round(base_cagr_pct, 4)},
        "bull": {"terminal_price": round(_price(bull_cagr), 4), "cagr_pct": round(bull_cagr, 4)},
    }
    return scenarios, capped


# ---------------------------------------------------------------------------
# Guardrail #10 — confidence score
# ---------------------------------------------------------------------------

def compute_confidence(
    *, cagr_status: str, history_flag: str | None, regime_flagged: bool, high_volatility: bool,
    drawdown_risk: bool, insufficient_history: bool, data_quality_status: str, terminal_cap_applied: bool,
    cfg: Any,
) -> tuple[float, str]:
    score = float(_cfg(cfg, "confidence", "base_score"))
    if cagr_status in ("EXTREME_GROWTH", "EXTREME_DOWNSIDE"):
        score -= float(_cfg(cfg, "confidence", "penalty_extreme_cagr"))
    elif cagr_status in ("HIGH_GROWTH", "HIGH_DOWNSIDE"):
        score -= float(_cfg(cfg, "confidence", "penalty_high_cagr"))
    if history_flag:
        score -= float(_cfg(cfg, "confidence", "penalty_history_deviation"))
    if regime_flagged:
        score -= float(_cfg(cfg, "confidence", "penalty_regime_shift"))
    if high_volatility:
        score -= float(_cfg(cfg, "confidence", "penalty_high_volatility"))
    if drawdown_risk:
        score -= float(_cfg(cfg, "confidence", "penalty_drawdown_risk"))
    if insufficient_history:
        score -= float(_cfg(cfg, "confidence", "penalty_insufficient_history"))
    if data_quality_status in ("DEGRADED", "INVALID"):
        score -= float(_cfg(cfg, "confidence", "penalty_data_quality"))
    if terminal_cap_applied:
        score -= float(_cfg(cfg, "confidence", "penalty_terminal_cap"))
    score = max(0.0, min(100.0, score))
    if score >= 80:
        status = "HIGHER_CONFIDENCE"
    elif score >= 60:
        status = "MODERATE_CONFIDENCE"
    elif score >= 40:
        status = "LOW_CONFIDENCE"
    else:
        status = "VERY_LOW_CONFIDENCE"
    return score, status


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_guardrails(
    *,
    raw_mu: float,
    sigma_annual: float,
    raw_price_series: pd.Series | None,
    clean_prices: pd.Series | None,
    log_returns: np.ndarray | None,
    horizon_years: float,
    is_fallback_method: bool,
    config: Any,
) -> ForecastGuardrailResult:
    """Guard a single instrument's Transformer-derived `raw_mu`.

    This is an engineering reliability check, not a claim that
    `guarded_mu`/`scenarios` are accurate predictions of the future.
    """
    flags: list[str] = []
    warnings: list[str] = []

    data_quality_status, dq_flags, dq_warnings = check_data_quality(
        raw_price_series, clean_prices, log_returns, config,
    )
    flags.extend(dq_flags)
    warnings.extend(dq_warnings)

    raw_mu_safe = raw_mu if _finite(raw_mu) else 0.0
    sigma_safe = sigma_annual if _finite(sigma_annual) and sigma_annual >= 0 else 0.0
    if not _finite(raw_mu) or not _finite(sigma_annual):
        flags.append("NONFINITE_INPUT_SANITIZED")
        warnings.append("Forecast input contained a non-finite value; it was replaced with a safe default.")

    current_price: float | None = None
    if clean_prices is not None and len(clean_prices):
        cp = float(clean_prices.iloc[-1])
        if _finite(cp) and cp > 0:
            current_price = cp
    if current_price is None:
        flags.append("INVALID_CURRENT_PRICE")
        warnings.append("No valid current price is available; forecast outputs are suppressed.")

    insufficient_history = is_fallback_method or "INSUFFICIENT_HISTORY" in dq_flags
    if is_fallback_method and "INSUFFICIENT_HISTORY" not in flags:
        flags.append("INSUFFICIENT_HISTORY")
        warnings.append("Not enough price history to train the Transformer; using the historical-mean fallback.")

    raw_cagr_pct = raw_mu_safe * 100.0
    cagr_status = classify_cagr(raw_cagr_pct, config)
    if cagr_status != "NORMAL_RANGE":
        flags.append(cagr_status)
        warnings.append(f"Raw forecast CAGR ({raw_cagr_pct:.1f}%) falls in the {cagr_status} band.")

    guarded_cagr_pct, soft_cap_applied = apply_soft_cap(raw_cagr_pct, sigma_safe, config)
    if soft_cap_applied:
        flags.append("SOFT_CAP_APPLIED")
        warnings.append(
            f"Raw CAGR ({raw_cagr_pct:.1f}%) was shrunk toward the (volatility-scaled) soft cap, to "
            f"{guarded_cagr_pct:.1f}%, before reaching the optimizer."
        )

    guarded_cagr_pct, terminal_cap_applied = apply_terminal_multiple_cap(guarded_cagr_pct, sigma_safe, horizon_years, config)
    if terminal_cap_applied:
        max_multiple = effective_terminal_max_multiple(sigma_safe, config)
        flags.append("TERMINAL_PRICE_CAP_APPLIED")
        warnings.append(
            f"Guarded forecast would have projected more than {max_multiple:.2f}x the current price/invested "
            f"amount over {horizon_years:g} years; hard-capped to {max_multiple:.2f}x ({guarded_cagr_pct:.1f}% CAGR)."
        )
    guarded_mu = guarded_cagr_pct / 100.0

    hist_cagr_pct = hist_years = None
    if clean_prices is not None:
        hist_cagr, hist_years = best_historical_cagr(clean_prices)
        if hist_cagr is not None:
            hist_cagr_pct = hist_cagr * 100.0
    min_years = float(_cfg(config, "historical", "min_years_for_comparison"))
    history_flag = None
    if hist_cagr_pct is not None and (hist_years or 0) >= min_years:
        history_flag, history_warning = compare_to_history(raw_cagr_pct, hist_cagr_pct, config)
        if history_flag:
            flags.append(history_flag)
            warnings.append(history_warning)

    drawdown_pct = max_drawdown_pct(clean_prices)
    high_pos_threshold = float(_cfg(config, "cagr", "high_positive_pct"))
    drawdown_threshold = float(_cfg(config, "drawdown", "high_drawdown_pct"))
    drawdown_risk = (
        drawdown_pct is not None and drawdown_pct <= drawdown_threshold and guarded_cagr_pct > high_pos_threshold
    )
    if drawdown_risk:
        flags.append("HIGH_DRAWDOWN_RISK")
        warnings.append(
            f"Historical max drawdown ({drawdown_pct:.1f}%) is severe relative to the optimistic "
            f"forecast ({guarded_cagr_pct:.1f}% CAGR)."
        )

    regime = regime_shift(log_returns, config) if bool(_cfg(config, "regime", "enabled")) else {"flagged": False}
    if regime.get("flagged"):
        flags.append("REGIME_SHIFT")
        warnings.append("Recent volatility regime differs substantially from the instrument's historical volatility.")

    high_volatility = sigma_safe * 100.0 > float(_cfg(config, "volatility", "high_annual_pct"))
    if high_volatility:
        flags.append("HIGH_VOLATILITY")
        warnings.append(f"Historical annualized volatility ({sigma_safe * 100:.1f}%) is high.")

    confidence_score, confidence_status = compute_confidence(
        cagr_status=cagr_status, history_flag=history_flag, regime_flagged=bool(regime.get("flagged")),
        high_volatility=high_volatility, drawdown_risk=drawdown_risk, insufficient_history=insufficient_history,
        data_quality_status=data_quality_status, terminal_cap_applied=terminal_cap_applied, cfg=config,
    )

    if current_price is not None:
        raw_terminal_price = current_price * (1.0 + raw_mu_safe) ** horizon_years
        guarded_terminal_price = current_price * (1.0 + guarded_mu) ** horizon_years
        if not _finite(raw_terminal_price):
            raw_terminal_price = current_price
        if not _finite(guarded_terminal_price):
            guarded_terminal_price = current_price
        trajectory = build_trajectory(current_price, guarded_mu, horizon_years)
        scenarios, scenario_capped = build_scenarios(current_price, guarded_mu, sigma_safe, horizon_years, config)
        if scenario_capped:
            flags.append("SCENARIO_CAPPED")
            warnings.append(
                "The bear/bull scenario band was capped to avoid implausible multi-year compounding; "
                "see scenario.max_cagr_pct/min_cagr_pct in config.yaml."
            )
        guardrail_status = cagr_status
    else:
        current_price = 0.0
        raw_terminal_price = 0.0
        guarded_terminal_price = 0.0
        trajectory = []
        scenarios = {}
        guarded_mu = 0.0
        guardrail_status = "DATA_QUALITY_ISSUE"

    return ForecastGuardrailResult(
        raw_mu=raw_mu_safe,
        guarded_mu=guarded_mu,
        sigma_annual=sigma_safe,
        current_price=current_price,
        raw_terminal_price=raw_terminal_price,
        guarded_terminal_price=guarded_terminal_price,
        raw_cagr_pct=raw_cagr_pct,
        guarded_cagr_pct=guarded_cagr_pct,
        historical_cagr_pct=hist_cagr_pct,
        historical_cagr_years=hist_years,
        historical_volatility_pct=sigma_safe * 100.0,
        historical_max_drawdown_pct=drawdown_pct,
        confidence_score=confidence_score,
        confidence_status=confidence_status,
        guardrail_status=guardrail_status,
        data_quality_status=data_quality_status,
        soft_cap_applied=soft_cap_applied,
        terminal_cap_applied=terminal_cap_applied,
        flags=flags,
        warnings=warnings,
        trajectory=trajectory,
        scenarios=scenarios,
        metadata={"regime": regime, "horizon_years_used": horizon_years},
    )
