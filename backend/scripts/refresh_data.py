"""Refresh the app's data in one go: latest prices, fund NAVs and FD rates, then the forecasts.

    python scripts/refresh_data.py              # prices and NAVs, forecasts only where missing or old
    python scripts/refresh_data.py --forecasts  # also recompute every forecast

The running app only reads the database, so this can run beside it. The database is put in WAL mode first, which lets the app
keep reading while the download writes. Used by scripts/scheduler.py (the deployed app) and by hand."""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from sqlalchemy import text

logger = logging.getLogger("refresh")


def run_refresh(force_forecasts: bool = False) -> dict:
    import download
    from backend.db import get_engine
    from warm_forecasts import warm

    started = time.time()
    with get_engine().connect() as conn:                         # readers and the writer no longer block each other
        conn.execute(text("PRAGMA journal_mode=WAL"))
    summary = download.run()
    if not summary.get("ok"):
        raise RuntimeError(f"the download refreshed nothing: {summary}")
    ready, skipped = warm(force_forecasts)
    result = {"downloaded": summary["ok"], "failed": summary["failed"], "forecasts": ready, "skipped": skipped,
              "seconds": round(time.time() - started)}
    logger.info("refresh complete: %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--forecasts", action="store_true", help="recompute every forecast, not only the missing ones")
    args = ap.parse_args()
    print(run_refresh(args.forecasts))
