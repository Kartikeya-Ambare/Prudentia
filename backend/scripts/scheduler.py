"""The deployed app's own scheduler: refreshes the data every weekday evening, with no outside cron and no laptop involved.

    python scripts/scheduler.py

REFRESH_TIME (default 20:30) and REFRESH_TZ (default Asia/Kolkata) say when. Prices do not change at weekends, so Saturday
and Sunday are skipped. Forecasts are recomputed in full on Fridays and only filled in on the other days. On start-up it
refreshes at once if the newest price is more than 3 days old (a new server, or one that was switched off)."""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("scheduler")

TZ = ZoneInfo(os.environ.get("REFRESH_TZ", "Asia/Kolkata"))
HOUR, MINUTE = (int(x) for x in os.environ.get("REFRESH_TIME", "20:30").split(":"))
STALE_DAYS = 3


def next_run(now: datetime) -> datetime:
    """The next weekday at REFRESH_TIME that is still in the future."""
    when = now.replace(hour=HOUR, minute=MINUTE, second=0, microsecond=0)
    while when <= now or when.weekday() >= 5:
        when = (when + timedelta(days=1)).replace(hour=HOUR, minute=MINUTE, second=0, microsecond=0)
    return when


def newest_price() -> date | None:
    from sqlalchemy import func, select
    from backend.db import get_engine, prices
    with get_engine().connect() as conn:
        newest = conn.execute(select(func.max(prices.c.date))).scalar()
    return date.fromisoformat(str(newest)) if newest else None


def refresh(now: datetime) -> None:
    from refresh_data import run_refresh
    try:
        run_refresh(force_forecasts=now.weekday() == 4)           # Friday: recompute every forecast
    except Exception:                                             # a failed night must not stop the next one
        log.exception("refresh failed; the app keeps the data it has and the scheduler tries again at the next slot")


def main() -> None:
    time.sleep(int(os.environ.get("SCHEDULER_START_DELAY", "60")))   # let the backend start first
    now = datetime.now(TZ)
    try:
        newest = newest_price()
    except Exception:
        log.exception("could not read the newest price date")
        newest = None
    if newest is None or (now.date() - newest).days > STALE_DAYS:
        log.info("newest price is %s: refreshing now", newest)
        refresh(now)
    while True:
        now = datetime.now(TZ)
        when = next_run(now)
        log.info("next refresh: %s", when.isoformat(timespec="minutes"))
        time.sleep(max(1.0, (when - now).total_seconds()))
        refresh(datetime.now(TZ))


if __name__ == "__main__":
    main()
