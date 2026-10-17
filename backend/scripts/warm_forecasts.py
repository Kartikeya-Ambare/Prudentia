"""Compute (or reuse) the cached forecast of every stock and fund in the database, so no plan request ever has to train a model.

    python scripts/warm_forecasts.py            # only what is missing or older than forecaster.cache_max_age_hours
    python scripts/warm_forecasts.py --force    # recompute everything (after a fresh data download)

Run it after download.py and before a demo. It can take several minutes the first time; later runs are quick."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from backend.data.cache_manager import get_mf_nav, get_prices
from backend.db import get_engine, mf_nav, prices
from backend.forecasting.forecaster import forecast_ticker


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="recompute even when a recent forecast is cached")
    force = ap.parse_args().force
    with get_engine().connect() as conn:
        tickers = sorted({r[0] for r in conn.execute(select(prices.c.ticker).distinct())})
        codes = sorted({str(r[0]) for r in conn.execute(select(mf_nav.c.scheme_code).distinct())})
    jobs = [(t, "stock") for t in tickers] + [(c, "mf") for c in codes]
    start = time.time()
    ok = bad = 0
    for i, (label, kind) in enumerate(jobs, 1):
        try:
            df = get_prices(label) if kind == "stock" else get_mf_nav(label)
            series = df["adj_close"] if kind == "stock" else df["nav"]
            if series is None or series.empty:
                continue
            forecast_ticker(label, series, force_refresh=force)
            ok += 1
        except Exception as exc:                        # one bad series must not stop the rest
            bad += 1
            print(f"  skipped {label}: {exc}", flush=True)
        if i % 20 == 0 or i == len(jobs):
            print(f"{i}/{len(jobs)} done, {time.time() - start:.0f}s", flush=True)
    print(f"warm-up finished: {ok} forecasts ready, {bad} skipped, {time.time() - start:.0f}s", flush=True)


if __name__ == "__main__":
    main()
