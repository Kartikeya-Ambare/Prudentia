"""Thin DB-read layer. The live app never calls yfinance/mfapi/scrapers
directly — it only ever reads what download.py already wrote here. Interface
kept identical across the download.py rewrite: get_prices(ticker) still
returns a DataFrame indexed by date with the same columns it always had.
"""
from __future__ import annotations

import threading
import time

import pandas as pd
from sqlalchemy import func, select

from backend.db import download_runs, fundamentals, get_engine, mf_nav, mf_sector_allocation, prices

# --- in-memory memo of the two big history reads --------------------------------------------------------------
# One plan request reads the same price / NAV history hundreds of times (and the orchestrator reads some twice).
# The history only changes when download.py finishes a run, so the result of each read is kept in memory and thrown
# away as soon as a newer download run is recorded (or after 10 minutes, as a safety net). Callers get a copy, so
# nothing they do to the frame can leak into the next request. Values returned are identical to an uncached read.
_MEMO_LOCK = threading.Lock()
_MEMO: dict = {"stamp": None, "checked": 0.0, "born": 0.0, "prices": {}, "nav": {}}
_STAMP_EVERY = 2.0      # seconds between "has a new download run finished?" checks
_MAX_AGE = 600.0        # seconds


def _fresh_memo() -> None:
    """Empty the memo when a newer download run has finished (cheap tiny-table query, at most every 2 s)."""
    now = time.monotonic()
    if now - _MEMO["checked"] < _STAMP_EVERY and now - _MEMO["born"] < _MAX_AGE:
        return
    with get_engine().connect() as conn:
        stamp = conn.execute(select(func.max(download_runs.c.finished_at))).scalar()
    _MEMO["checked"] = now
    if stamp != _MEMO["stamp"] or now - _MEMO["born"] >= _MAX_AGE:
        _MEMO.update(stamp=stamp, born=now, prices={}, nav={})


def _read(kind: str, key: str, loader) -> pd.DataFrame:
    with _MEMO_LOCK:
        _fresh_memo()
        hit = _MEMO[kind].get(key)
    if hit is None:
        hit = loader()
        with _MEMO_LOCK:
            _MEMO[kind][key] = hit
    return hit.copy()


def get_prices(ticker: str, force_refresh: bool = False) -> pd.DataFrame:
    """force_refresh is accepted for interface compatibility but ignored —
    the live app is never allowed to trigger a live fetch; only download.py does."""
    return _read("prices", ticker, lambda: _load_prices(ticker))


def _load_prices(ticker: str) -> pd.DataFrame:
    engine = get_engine()
    query = select(prices).where(prices.c.ticker == ticker).order_by(prices.c.date)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    if not df.empty:
        df = df.set_index("date")
    return df


def get_mf_nav(scheme_code: str) -> pd.DataFrame:
    return _read("nav", scheme_code, lambda: _load_nav(scheme_code))


def _load_nav(scheme_code: str) -> pd.DataFrame:
    engine = get_engine()
    query = select(mf_nav).where(mf_nav.c.scheme_code == scheme_code).order_by(mf_nav.c.date)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    if not df.empty:
        df = df.set_index("date")
    return df


def warm_cache() -> None:
    """Read every stock's price history and every fund's NAV history into the memo (run once in the background at
    start-up, so the first plan request is as fast as the later ones). Safe to call at any time."""
    engine = get_engine()
    with engine.connect() as conn:
        tickers = [r[0] for r in conn.execute(select(prices.c.ticker).distinct())]
        codes = [r[0] for r in conn.execute(select(mf_nav.c.scheme_code).distinct())]
    for t in tickers:
        get_prices(t)
    for c in codes:
        get_mf_nav(c)


def get_latest_sector_allocation(scheme_code: str) -> dict | None:
    engine = get_engine()
    query = (
        select(mf_sector_allocation)
        .where(mf_sector_allocation.c.scheme_code == scheme_code)
        .order_by(mf_sector_allocation.c.date.desc())
        .limit(1)
    )
    with engine.connect() as conn:
        row = conn.execute(query).mappings().first()
    return dict(row) if row else None


def get_sector_history(scheme_code: str) -> list[dict]:
    engine = get_engine()
    query = (
        select(mf_sector_allocation)
        .where(mf_sector_allocation.c.scheme_code == scheme_code)
        .order_by(mf_sector_allocation.c.date.asc())
    )
    with engine.connect() as conn:
        rows = conn.execute(query).mappings().all()
    return [dict(r) for r in rows]


def list_mf_schemes_with_sector_data() -> list[dict]:
    """{scheme_code, last_updated} for every scheme the daily scraper has
    successfully collected at least one sector-allocation snapshot for."""
    engine = get_engine()
    query = (
        select(mf_sector_allocation.c.scheme_code, func.max(mf_sector_allocation.c.date).label("last_updated"))
        .group_by(mf_sector_allocation.c.scheme_code)
    )
    with engine.connect() as conn:
        rows = conn.execute(query).mappings().all()
    return [dict(r) for r in rows]
