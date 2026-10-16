#!/usr/bin/env python
"""Once-daily, multi-threaded bulk downloader. Populates the DB from the
*entire* universe — the live app (backend/data/cache_manager.py) never
calls yfinance/mfapi directly, it only reads what this script wrote.

Run manually or from cron/Task Scheduler:
    python download.py                # full universe
    python download.py --limit 5      # smoke-test a handful of instruments
    python download.py --skip-mf       # stocks + bank rates only
"""
from __future__ import annotations

import argparse
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import requests
import yaml
import yfinance as yf

from backend.config import get_config, repo_path
from backend.data.universe_builder import resolve_all_seeds
from backend.db import bank_rates, download_runs, get_engine, init_db, mf_nav, prices

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("download")


def _chunk(seq: list, size: int) -> list[list]:
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def _f(v) -> float | None:
    try:
        f = float(v)
        return f if f == f else None  # filter NaN
    except (TypeError, ValueError):
        return None


def _upsert(engine, table, rows: list[dict], pk_cols: list[str]) -> None:
    if not rows:
        return
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as dialect_insert
        elif dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as dialect_insert
        else:
            for row in rows:
                conn.execute(table.delete().where(
                    *[table.c[c] == row[c] for c in pk_cols]))
            conn.execute(table.insert(), rows)
            return

        # SQLite's default build caps bound parameters per statement at 999;
        # a single instrument's multi-year price/NAV history (len(rows) *
        # len(columns)) blows past that in one `.values(rows)` call, so this
        # chunks the insert to stay safely under the limit regardless of
        # table width. Harmless on Postgres too (just more round-trips).
        max_vars_per_statement = 900
        chunk_size = max(1, max_vars_per_statement // len(table.columns))
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i:i + chunk_size]
            stmt = dialect_insert(table).values(chunk)
            update_cols = {c.name: stmt.excluded[c.name] for c in table.columns if c.name not in pk_cols}
            stmt = stmt.on_conflict_do_update(index_elements=pk_cols, set_=update_cols)
            conn.execute(stmt)


def load_universe(cfg) -> tuple[list[str], dict[str, str], list[dict]]:
    with open(repo_path(cfg.download.universe_file), encoding="utf-8") as f:
        stock_universe = yaml.safe_load(f)
    with open(repo_path(cfg.download.bank_universe_file), encoding="utf-8") as f:
        bank_universe = yaml.safe_load(f)

    tickers = [t for sector in stock_universe["sectors"].values() for t in sector["tickers"]]
    resolved = resolve_all_seeds(repo_path(cfg.download.mf_universe_file))
    resolved = {name: code for name, code in resolved.items() if code}
    return tickers, resolved, bank_universe["banks"]


def download_stock_batch(tickers: list[str], lookback_days: int) -> tuple[list[dict], list[str]]:
    rows, failed = [], []
    end = datetime.now()
    start = end - timedelta(days=lookback_days)
    try:
        data = yf.download(tickers, start=start.date(), end=end.date(), group_by="ticker",
                            auto_adjust=False, threads=False, progress=False)
    except Exception as exc:
        logger.warning("stock batch fetch failed for %s: %s", tickers, exc)
        return rows, list(tickers)

    for t in tickers:
        try:
            if len(tickers) == 1:
                df = data
            else:
                if t not in data.columns.get_level_values(0):
                    raise ValueError("ticker missing from response")
                df = data[t]
            df = df.dropna(how="all")
            if df.empty:
                raise ValueError("empty frame")
            for idx, r in df.iterrows():
                rows.append(dict(
                    ticker=t, date=idx.date(),
                    open=_f(r.get("Open")), high=_f(r.get("High")), low=_f(r.get("Low")),
                    close=_f(r.get("Close")), adj_close=_f(r.get("Adj Close")), volume=_f(r.get("Volume")),
                ))
        except Exception as exc:
            logger.info("stock %s failed: %s", t, exc)
            failed.append(t)
    return rows, failed


def download_mf_batch(pairs: list[tuple[str, str]]) -> tuple[list[dict], list[tuple[str, str]]]:
    rows, failed = [], []
    for name, code in pairs:
        try:
            resp = requests.get(f"https://api.mfapi.in/mf/{code}", timeout=15)
            resp.raise_for_status()
            payload = resp.json()
            for point in payload.get("data", []):
                nav = _f(point.get("nav"))
                if nav is None:
                    continue
                d = datetime.strptime(point["date"], "%d-%m-%Y").date()
                rows.append(dict(scheme_code=code, date=d, nav=nav))
        except Exception as exc:
            logger.info("MF %s (%s) failed: %s", name, code, exc)
            failed.append((name, code))
    return rows, failed


def _stock_worker(batch, lookback_days, retries, delay) -> dict:
    rows, failed = download_stock_batch(batch, lookback_days)
    if failed and retries > 0:
        retry_rows, failed = download_stock_batch(failed, lookback_days)
        rows.extend(retry_rows)
    time.sleep(delay)
    return {"batch": batch, "rows": rows, "failed": failed}


def _mf_worker(batch, retries, delay) -> dict:
    rows, failed = download_mf_batch(batch)
    if failed and retries > 0:
        retry_rows, failed = download_mf_batch(failed)
        rows.extend(retry_rows)
    time.sleep(delay)
    return {"batch": batch, "rows": rows, "failed": failed}


def refresh_bank_rates(engine, banks: list[dict]) -> None:
    today = datetime.now().date()
    rows = [dict(bank_id=b["id"], as_of=today, fd_rate_pct=b["rate_pct"]) for b in banks]
    _upsert(engine, bank_rates, rows, ["bank_id", "as_of"])
    logger.info("refreshed FD rates for %d banks", len(rows))


def run(limit: int | None = None, skip_mf: bool = False, skip_stocks: bool = False) -> dict:
    cfg = get_config()
    engine = init_db()
    tickers, mf_resolved, banks = load_universe(cfg)

    if limit:
        tickers = tickers[:limit]
        mf_resolved = dict(list(mf_resolved.items())[:limit])

    run_id = str(uuid.uuid4())
    started_at = datetime.now()
    ok, failed_list = 0, []

    workers = cfg.download.workers
    delay = cfg.download.inter_batch_delay_seconds
    retries = cfg.download.max_retries

    jobs = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        if not skip_stocks:
            for batch in _chunk(tickers, cfg.download.batch_size):
                jobs.append(executor.submit(_stock_worker, batch, cfg.download.lookback_days, retries, delay))
        if not skip_mf:
            for batch in _chunk(list(mf_resolved.items()), cfg.download.batch_size):
                jobs.append(executor.submit(_mf_worker, batch, retries, delay))

        for fut in as_completed(jobs):
            result = fut.result()
            is_mf = result["batch"] and isinstance(result["batch"][0], tuple)
            table = mf_nav if is_mf else prices
            pk = ["scheme_code", "date"] if is_mf else ["ticker", "date"]
            try:
                _upsert(engine, table, result["rows"], pk)
                ok += len(result["batch"]) - len(result["failed"])
                failed_list.extend(result["failed"])
            except Exception as exc:
                # A DB write failure for one batch must not take down a run
                # that's otherwise successfully fetched the rest of the
                # universe.
                logger.error("DB upsert failed for batch %s: %s", result["batch"], exc)
                failed_list.extend(result["batch"])

    refresh_bank_rates(engine, banks)

    finished_at = datetime.now()
    with engine.begin() as conn:
        conn.execute(download_runs.insert().values(
            run_id=run_id, started_at=started_at, finished_at=finished_at,
            tickers_ok=ok, tickers_failed=len(failed_list),
            notes=", ".join(str(f) for f in failed_list[:50]),
        ))

    summary = {"run_id": run_id, "ok": ok, "failed": len(failed_list), "failed_list": failed_list,
               "duration_s": (finished_at - started_at).total_seconds()}
    logger.info("download run complete: %s", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                         help="only process the first N stock tickers / N resolved MF schemes (smoke test)")
    parser.add_argument("--skip-mf", action="store_true")
    parser.add_argument("--skip-stocks", action="store_true")
    args = parser.parse_args()
    run(limit=args.limit, skip_mf=args.skip_mf, skip_stocks=args.skip_stocks)
