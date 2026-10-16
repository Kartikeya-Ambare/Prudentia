from sqlalchemy import inspect

from backend.db import init_db


def test_init_db_creates_all_tables():
    engine = init_db()
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    expected = {
        "prices", "mf_nav", "fundamentals", "download_runs", "bank_rates",
        "mf_sector_allocation", "scrape_runs", "bank_pick_history", "profile_allocations",
    }
    assert expected.issubset(tables)
