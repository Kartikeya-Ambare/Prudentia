import importlib.util
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

spec = importlib.util.spec_from_file_location("scheduler", Path(__file__).resolve().parents[1] / "scripts" / "scheduler.py")
scheduler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduler)

IST = ZoneInfo("Asia/Kolkata")


def at(y, m, d, h, mi):
    return datetime(y, m, d, h, mi, tzinfo=IST)


def test_before_the_time_it_runs_today():
    assert scheduler.next_run(at(2026, 10, 19, 10, 0)) == at(2026, 10, 19, 20, 30)      # a Monday


def test_after_the_time_it_runs_tomorrow():
    assert scheduler.next_run(at(2026, 10, 19, 21, 0)) == at(2026, 10, 20, 20, 30)


def test_friday_evening_waits_for_monday():
    assert scheduler.next_run(at(2026, 10, 16, 21, 0)) == at(2026, 10, 19, 20, 30)      # Friday night -> Monday


def test_weekend_waits_for_monday():
    assert scheduler.next_run(at(2026, 10, 17, 9, 0)) == at(2026, 10, 19, 20, 30)       # Saturday
    assert scheduler.next_run(at(2026, 10, 18, 22, 0)) == at(2026, 10, 19, 20, 30)      # Sunday
