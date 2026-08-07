"""generate_synthetic_prices.py — deterministic synthetic OHLCV/NAV generator.

Anyone on the team can run this and get BYTE-IDENTICAL price series to everyone else who runs
it, on any machine, any Python version, any day — that's what "no tight coupling" actually
requires: not a shared file everyone has to keep in sync, but a shared *recipe* that always
produces the same output.

IMPORTANT — why this uses hashlib and NOT Python's built-in hash():
forecaster.py (the locked reference implementation, CLAUDE.md §7) seeds its per-instrument model
init via `abs(hash(instrument_name)) % 2**32`. That's fine *within* a single run for
decorrelating instruments from each other, but Python's built-in hash() of a string is
randomized per-process by default (hash randomization, on since Python 3.3) unless the
PYTHONHASHSEED env var is fixed. Two team members running forecaster.py on two machines will
NOT get identical mu/sigma out of it unless they both set PYTHONHASHSEED=0.
This generator intentionally uses hashlib.md5 instead, specifically so the DUMMY DATA itself is
reproducible everywhere without anyone needing to set an env var. If exact forecaster.py-output
reproducibility across machines ever matters (e.g. for a written-up ablation table), the team
should set PYTHONHASHSEED=0 in their shared dev env — that's a forecaster.py concern, orthogonal
to this fixture generator.

Usage:
    python generate_synthetic_prices.py --out ./prices --days 300

Produces one CSV per instrument: date, open, high, low, close, volume (stocks) or
date, nav (mutual funds), plus a manifest.json summarizing what was generated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

TRADING_DAYS_PER_YEAR = 252


def deterministic_seed(name: str) -> int:
    """Same idea as forecaster.py's per-instrument seed, but reproducible across machines."""
    return int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % (2**32)


def gbm_series(seed: int, days: int, start_price: float, annual_mu: float, annual_sigma: float) -> np.ndarray:
    """Geometric Brownian Motion daily close series -- deterministic given the seed."""
    rng = np.random.default_rng(seed)
    dt = 1 / TRADING_DAYS_PER_YEAR
    daily_mu = annual_mu * dt
    daily_sigma = annual_sigma * np.sqrt(dt)
    shocks = rng.normal(daily_mu - 0.5 * daily_sigma**2, daily_sigma, size=days)
    log_prices = np.log(start_price) + np.cumsum(shocks)
    return np.exp(log_prices)


def build_stock_ohlcv(ticker: str, days: int, start_price: float, annual_mu: float, annual_sigma: float) -> pd.DataFrame:
    seed = deterministic_seed(ticker)
    closes = gbm_series(seed, days, start_price, annual_mu, annual_sigma)
    rng = np.random.default_rng(seed + 1)  # offset so intraday range isn't perfectly correlated with the seed used for closes
    intraday_range_pct = rng.uniform(0.005, 0.02, size=days)
    opens = np.roll(closes, 1)
    opens[0] = start_price
    highs = np.maximum(opens, closes) * (1 + intraday_range_pct)
    lows = np.minimum(opens, closes) * (1 - intraday_range_pct)
    volumes = rng.integers(500_000, 5_000_000, size=days)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize() - pd.Timedelta(days=1), periods=days)
    return pd.DataFrame({"date": dates, "open": opens.round(2), "high": highs.round(2),
                          "low": lows.round(2), "close": closes.round(2), "volume": volumes})


def build_mf_nav(scheme_code: str, days: int, start_nav: float, annual_mu: float, annual_sigma: float) -> pd.DataFrame:
    seed = deterministic_seed(scheme_code)
    navs = gbm_series(seed, days, start_nav, annual_mu, annual_sigma)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize() - pd.Timedelta(days=1), periods=days)
    return pd.DataFrame({"date": dates, "nav": navs.round(4)})


# Rough, plausible annual (mu, sigma) per instrument -- NOT real market data, just realistic-
# enough dummy assumptions so downstream KPI/optimizer math doesn't produce nonsense.
STOCK_PARAMS = {
    "TCS.NS":        dict(start_price=3850, mu=0.14, sigma=0.22),
    "INFY.NS":       dict(start_price=1650, mu=0.13, sigma=0.24),
    "HDFCBANK.NS":   dict(start_price=1680, mu=0.15, sigma=0.20),
    "ICICIBANK.NS":  dict(start_price=1220, mu=0.16, sigma=0.23),
    "RELIANCE.NS":   dict(start_price=2950, mu=0.11, sigma=0.21),
    "ITC.NS":        dict(start_price=460,  mu=0.09, sigma=0.16),
    "SUNPHARMA.NS":  dict(start_price=1780, mu=0.12, sigma=0.19),
    "MARUTI.NS":     dict(start_price=12500, mu=0.10, sigma=0.25),
}

MF_PARAMS = {
    "HDFC_FLEXICAP":        dict(start_nav=1850.0, mu=0.13, sigma=0.18),
    "SBI_BLUECHIP":         dict(start_nav=92.0,   mu=0.12, sigma=0.16),
    "AXIS_MIDCAP":          dict(start_nav=105.0,  mu=0.15, sigma=0.22),
    "PARAGPARIKH_FLEXICAP": dict(start_nav=88.0,   mu=0.14, sigma=0.17),
    "ICICIPRU_SHORTDEBT":   dict(start_nav=45.0,   mu=0.065, sigma=0.03),  # debt fund -- low mu, low sigma
}


def build_correlation_test_set(days: int) -> dict[str, pd.DataFrame]:
    """Three series purpose-built for M4's universe_selector.py dedup test:
    CORR_A and CORR_B are near-duplicates (correlation > 0.9, should trigger dedup),
    CORR_C is independent (should survive alongside whichever of A/B wins the tiebreak).
    This is deliberately NOT left to chance the way the main GBM series are -- independent
    GBM walks are not reliably correlated over 300 days, so M4 needs a fixture that
    guarantees a correlated pair exists to test against.
    """
    seed = deterministic_seed("CORRELATION_TEST_SET")
    rng = np.random.default_rng(seed)
    base_shocks = rng.normal(0.0003, 0.015, size=days)
    noise_a = rng.normal(0, 0.0015, size=days)   # small independent noise layered on the shared base
    noise_b = rng.normal(0, 0.0015, size=days)
    independent_shocks = rng.normal(0.0002, 0.017, size=days)  # unrelated to the base series

    price_a = 500 * np.exp(np.cumsum(base_shocks + noise_a))
    price_b = 500 * np.exp(np.cumsum(base_shocks + noise_b))
    price_c = 300 * np.exp(np.cumsum(independent_shocks))

    dates = pd.bdate_range(end=pd.Timestamp.today().normalize() - pd.Timedelta(days=1), periods=days)
    return {
        "CORR_A": pd.DataFrame({"date": dates, "close": price_a.round(2)}),
        "CORR_B": pd.DataFrame({"date": dates, "close": price_b.round(2)}),
        "CORR_C": pd.DataFrame({"date": dates, "close": price_c.round(2)}),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="./prices")
    ap.add_argument("--days", type=int, default=300)
    ap.add_argument("--universe", default="./universe.yaml")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"days": args.days, "generated_instruments": []}

    for ticker, params in STOCK_PARAMS.items():
        df = build_stock_ohlcv(ticker, args.days, params["start_price"], params["mu"], params["sigma"])
        df.to_csv(out_dir / f"{ticker}.csv", index=False)
        manifest["generated_instruments"].append({"id": ticker, "type": "stock", "seed": deterministic_seed(ticker)})

    for scheme, params in MF_PARAMS.items():
        df = build_mf_nav(scheme, args.days, params["start_nav"], params["mu"], params["sigma"])
        df.to_csv(out_dir / f"{scheme}.csv", index=False)
        manifest["generated_instruments"].append({"id": scheme, "type": "mf", "seed": deterministic_seed(scheme)})

    corr_dir = out_dir.parent / "correlation_test"
    corr_dir.mkdir(parents=True, exist_ok=True)
    corr_set = build_correlation_test_set(args.days)
    for name, df in corr_set.items():
        df.to_csv(corr_dir / f"{name}.csv", index=False)
    actual_corr_ab = corr_set["CORR_A"]["close"].pct_change().corr(corr_set["CORR_B"]["close"].pct_change())
    actual_corr_ac = corr_set["CORR_A"]["close"].pct_change().corr(corr_set["CORR_C"]["close"].pct_change())
    manifest["correlation_test_set"] = {
        "CORR_A_vs_CORR_B_correlation": round(float(actual_corr_ab), 4),
        "CORR_A_vs_CORR_C_correlation": round(float(actual_corr_ac), 4),
        "note": "M4's smoke test should assert A-vs-B correlation > 0.85 (dedup should trigger) and A-vs-C should not."
    }

    with open(out_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Wrote {len(manifest['generated_instruments'])} instrument CSVs + manifest.json to {out_dir}")
    print(f"Wrote correlation_test/ (CORR_A, CORR_B, CORR_C) to {corr_dir}")
    print(f"  A-vs-B correlation: {manifest['correlation_test_set']['CORR_A_vs_CORR_B_correlation']}")
    print(f"  A-vs-C correlation: {manifest['correlation_test_set']['CORR_A_vs_CORR_C_correlation']}")


if __name__ == "__main__":
    main()
