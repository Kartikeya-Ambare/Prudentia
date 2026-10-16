"""SQLAlchemy engine + schema.

Builds a Postgres URL from config.database when DB_HOST is set, otherwise
falls back to a local SQLite file (config.database.sqlite_fallback_path) so
the app runs with zero external services for dev/demo, per the CUDA-policy
style choice already made for this project: never require infrastructure the
user hasn't explicitly configured.
"""
from __future__ import annotations

from sqlalchemy import (
    Column, Date, DateTime, Float, ForeignKey, Integer, JSON, MetaData,
    PrimaryKeyConstraint, String, Table, Text, create_engine,
)
from sqlalchemy.engine import Engine

from backend.config import get_config, repo_path

metadata = MetaData()

prices = Table(
    "prices", metadata,
    Column("ticker", String, nullable=False),
    Column("date", Date, nullable=False),
    Column("open", Float),
    Column("high", Float),
    Column("low", Float),
    Column("close", Float),
    Column("adj_close", Float),
    Column("volume", Float),
    PrimaryKeyConstraint("ticker", "date"),
)

mf_nav = Table(
    "mf_nav", metadata,
    Column("scheme_code", String, nullable=False),
    Column("date", Date, nullable=False),
    Column("nav", Float),
    PrimaryKeyConstraint("scheme_code", "date"),
)

fundamentals = Table(
    "fundamentals", metadata,
    Column("ticker", String, nullable=False),
    Column("as_of", Date, nullable=False),
    Column("kpi_json", JSON),
    PrimaryKeyConstraint("ticker", "as_of"),
)

download_runs = Table(
    "download_runs", metadata,
    Column("run_id", String, primary_key=True),
    Column("started_at", DateTime),
    Column("finished_at", DateTime),
    Column("tickers_ok", Integer),
    Column("tickers_failed", Integer),
    Column("notes", Text),
)

bank_rates = Table(
    "bank_rates", metadata,
    Column("bank_id", String, nullable=False),
    Column("as_of", Date, nullable=False),
    Column("fd_rate_pct", Float),
    PrimaryKeyConstraint("bank_id", "as_of"),
)

mf_sector_allocation = Table(
    "mf_sector_allocation", metadata,
    Column("scheme_code", String, nullable=False),
    Column("date", Date, nullable=False),
    Column("sector_json", JSON),
    Column("source_url", Text),
    Column("fetched_at", DateTime),
    PrimaryKeyConstraint("scheme_code", "date"),
)

scrape_runs = Table(
    "scrape_runs", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("scheme_code", String, nullable=False),
    Column("run_at", DateTime),
    Column("status", String),
    Column("error_message", Text),
)

bank_pick_history = Table(
    "bank_pick_history", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("risk_bracket", String, nullable=False),
    Column("bank_id", String, nullable=False),
    Column("picked_at", DateTime),
)

profile_allocations = Table(
    "profile_allocations", metadata,
    Column("profile_id", String, primary_key=True),
    Column("mode", String),
    Column("risk_thermometer", Float),
    Column("horizon_years", Integer),
    Column("allocation_json", JSON),
    Column("updated_at", DateTime),
)


def _build_url() -> str:
    cfg = get_config().database
    host = cfg.get("host")
    if host:
        user, pwd, port, name = cfg.user, cfg.password, cfg.port, cfg.name
        return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{name}"
    fallback = repo_path(cfg.get("sqlite_fallback_path", "data/asset_allocation.db"))
    fallback.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{fallback}"


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(_build_url(), future=True)
    return _engine


def init_db() -> Engine:
    engine = get_engine()
    metadata.create_all(engine)
    return engine
