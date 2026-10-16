"""Risk-driven, correlation-based candidate selection. Narrows the
full stock/MF universe down to a per-bucket candidate pool the optimizer can
run over quickly. Only ever reads from the DB via cache_manager — never
touches yfinance/mfapi directly.
"""
from __future__ import annotations

import json
import math
from itertools import combinations

import numpy as np
import pandas as pd
import yaml

from backend.config import get_config, repo_path
from backend.data.cache_manager import get_mf_nav, get_prices

TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE = 0.065  # approx. Indian 10Y G-Sec, used only to rank by Sharpe within a candidate pool

MF_CATEGORY_LABEL_TO_KEY = {"Large Cap": "large_cap", "Mid Cap": "mid_cap", "Small Cap": "small_cap"}


def _load_yaml(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _risk_band_name(risk_thermometer: float, bands: dict) -> str:
    for name, rng in bands.items():
        if rng["min"] <= risk_thermometer <= rng["max"]:
            return name
    return "moderate"


def _clean_positive(series: pd.Series) -> pd.Series:
    """Drops NaN/None and non-positive values. Some sources (mfapi.in's
    older NAV history in particular) contain literal 0.0 rows from bad
    historical data — a zero survives dropna() and np.log(0.0) is -inf,
    which silently poisons every downstream mean/std/diff computation."""
    series = series.dropna()
    return series[series > 0]


def _annualized_volatility(series: pd.Series) -> float | None:
    series = _clean_positive(series)
    if len(series) < 2:
        return None
    log_returns = np.diff(np.log(series.values))
    if len(log_returns) < 2:
        return None
    return float(np.std(log_returns) * math.sqrt(TRADING_DAYS_PER_YEAR))


def _sharpe(series: pd.Series) -> float:
    series = _clean_positive(series)
    log_returns = np.diff(np.log(series.values))
    if len(log_returns) < 2:
        return 0.0
    mu = float(np.mean(log_returns) * TRADING_DAYS_PER_YEAR)
    sigma = float(np.std(log_returns) * math.sqrt(TRADING_DAYS_PER_YEAR))
    return 0.0 if sigma == 0 else (mu - RISK_FREE_RATE) / sigma


def _correlation_dedup(labels: list[str], price_cache: dict[str, pd.Series], threshold: float) -> list[str]:
    """ where rho > threshold, keep only the better-Sharpe instrument of the pair."""
    if len(labels) < 2:
        return labels
    returns = {}
    for label in labels:
        series = _clean_positive(price_cache[label])
        if len(series) >= 2:
            returns[label] = np.diff(np.log(series.values))

    dropped: set[str] = set()
    for a, b in combinations(returns.keys(), 2):
        if a in dropped or b in dropped:
            continue
        n = min(len(returns[a]), len(returns[b]))
        if n < 10:
            continue
        rho = float(np.corrcoef(returns[a][-n:], returns[b][-n:])[0, 1])
        if rho > threshold:
            worse = a if _sharpe(price_cache[a]) < _sharpe(price_cache[b]) else b
            dropped.add(worse)
    return [label for label in labels if label not in dropped]


def _volatility_filter(labels: list[str], price_cache: dict[str, pd.Series],
                        target_vol: float, tolerance: float, min_history: int) -> list[str]:
    survivors = []
    for label in labels:
        series = price_cache.get(label)
        if series is None or len(series) < min_history:
            survivors.append(label)  # not enough history to judge -- don't drop outright
            continue
        vol = _annualized_volatility(series)
        if vol is None or abs(vol - target_vol) <= tolerance * target_vol:
            survivors.append(label)

    if not survivors and labels:
        # A thin universe (or an extreme risk_thermometer with a narrow sector/
        # category preference) can leave zero instruments inside the target
        # volatility band. Silently returning an empty pool would zero out an
        # entire asset bucket for the user — instead, degrade to "risk band
        # advisory only" and keep every instrument download.py has actually
        # populated, rather than dropping the bucket.
        import logging
        logging.getLogger(__name__).warning(
            "volatility filter left zero candidates (target=%.1f%%, tolerance=%.0f%%) "
            "out of %d available -- falling back to unfiltered pool",
            target_vol * 100, tolerance * 100, len(labels),
        )
        return labels
    return survivors


def select_stock_candidates(risk_thermometer: float, sector_pref: list[str] | None = None) -> list[str]:
    cfg = get_config().selection
    bands = cfg.risk_bands.to_dict()
    band_name = _risk_band_name(risk_thermometer, bands)
    target_vol = bands[band_name]["target_vol_pct"] / 100.0
    tolerance = cfg.volatility_tolerance_pct / 100.0
    min_history = cfg.get("min_price_history_days", 60)

    stock_universe = _load_yaml(repo_path(get_config().download.universe_file))

    # step 0: scope by explicit sector preference (knowledgeable mode only)
    tickers: list[str] = []
    for key, sector in stock_universe["sectors"].items():
        if sector_pref and sector["display_name"] not in sector_pref and key not in sector_pref:
            continue
        tickers.extend(sector["tickers"])

    # only instruments download.py has actually populated are eligible
    price_cache: dict[str, pd.Series] = {}
    for ticker in tickers:
        df = get_prices(ticker)
        if not df.empty:
            price_cache[ticker] = df["adj_close"]
    available = list(price_cache.keys())

    # step 1: risk-band volatility filter
    survivors = _volatility_filter(available, price_cache, target_vol, tolerance, min_history)

    # step 2: correlation de-dup
    survivors = _correlation_dedup(survivors, price_cache, cfg.correlation_threshold)

    # step 3: cap pool size, ranked by Sharpe
    survivors.sort(key=lambda t: _sharpe(price_cache[t]), reverse=True)
    return survivors[: cfg.candidate_pool_size]


def _mf_category_weights(band_name: str) -> dict[str, float]:
    """Risk-band bias when the user hasn't explicitly picked a category
 — aggressive skews toward small-cap, conservative
    toward large-cap."""
    if band_name == "conservative":
        return {"large_cap": 0.6, "mid_cap": 0.3, "small_cap": 0.1}
    if band_name == "aggressive":
        return {"large_cap": 0.1, "mid_cap": 0.3, "small_cap": 0.6}
    return {"large_cap": 0.34, "mid_cap": 0.33, "small_cap": 0.33}


def select_mf_candidates(risk_thermometer: float, mf_category_pref: list[str] | None = None) -> list[str]:
    """Returns AMFI scheme codes (the runtime key)."""
    cfg = get_config().selection
    bands = cfg.risk_bands.to_dict()
    band_name = _risk_band_name(risk_thermometer, bands)

    mf_universe = _load_yaml(repo_path(get_config().download.mf_universe_file))
    code_cache_path = repo_path("universe", "mf_scheme_codes.json")
    name_to_code: dict[str, str | None] = (
        json.loads(code_cache_path.read_text(encoding="utf-8")) if code_cache_path.exists() else {}
    )

    pref_keys = (
        {MF_CATEGORY_LABEL_TO_KEY.get(p, p) for p in mf_category_pref} if mf_category_pref else None
    )

    per_category: dict[str, list[str]] = {}
    price_cache: dict[str, pd.Series] = {}
    for cat_key, cat in mf_universe["categories"].items():
        if pref_keys and cat_key not in pref_keys:
            continue
        codes = []
        for name in cat["seed_schemes"]:
            code = name_to_code.get(name)
            if not code:
                continue
            nav_df = get_mf_nav(code)
            if nav_df.empty:
                continue
            price_cache[code] = nav_df["nav"]
            codes.append(code)
        per_category[cat_key] = codes

    if pref_keys:
        pool_per_cat = {k: max(1, cfg.candidate_pool_size // len(pref_keys)) for k in pref_keys}
    else:
        weights = _mf_category_weights(band_name)
        pool_per_cat = {
            k: max(1, round(cfg.candidate_pool_size * weights.get(k, 0))) for k in per_category
        }

    selected: list[str] = []
    for cat_key, codes in per_category.items():
        codes = _correlation_dedup(codes, price_cache, cfg.correlation_threshold)
        codes.sort(key=lambda c: _sharpe(price_cache[c]), reverse=True)
        selected.extend(codes[: pool_per_cat.get(cat_key, 0)])

    return selected
