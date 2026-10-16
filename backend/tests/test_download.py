"""Regression test for a real bug caught during the full-universe smoke run:
a single instrument's multi-year price history in one bulk `.values(rows)`
upsert blew past SQLite's default 999-bound-variable-per-statement limit.
"""
from datetime import date, timedelta

from sqlalchemy import create_engine, func, select

import download
from backend.db import metadata, prices


def test_upsert_chunks_large_row_sets_under_sqlite_variable_limit():
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)

    # 7 columns * ~2000 rows = ~14000 bound variables in one naive INSERT --
    # comfortably over SQLite's 999 default limit if not chunked.
    rows = [
        dict(ticker="TEST.NS", date=date(2020, 1, 1) + timedelta(days=i),
             open=1.0, high=1.0, low=1.0, close=1.0, adj_close=1.0, volume=1.0)
        for i in range(2000)
    ]

    download._upsert(engine, prices, rows, ["ticker", "date"])

    with engine.connect() as conn:
        count = conn.execute(select(func.count()).select_from(prices)).scalar()
    assert count == 2000


def test_upsert_on_conflict_updates_existing_rows():
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)

    row = dict(ticker="TEST.NS", date=date(2020, 1, 1), open=1.0, high=1.0,
               low=1.0, close=1.0, adj_close=1.0, volume=100.0)
    download._upsert(engine, prices, [row], ["ticker", "date"])

    updated = dict(row, close=2.0, volume=200.0)
    download._upsert(engine, prices, [updated], ["ticker", "date"])

    with engine.connect() as conn:
        count = conn.execute(select(func.count()).select_from(prices)).scalar()
        stored = conn.execute(select(prices.c.close, prices.c.volume)).first()
    assert count == 1  # upsert, not duplicate insert
    assert stored.close == 2.0
    assert stored.volume == 200.0
