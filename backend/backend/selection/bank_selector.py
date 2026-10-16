"""Bank/FD selection. Scopes the bank universe by the FD-rate
band implied by risk_thermometer, then applies a weighted round-robin with a
recency penalty over the top-rate banks so the same bank isn't always the top
pick for a given risk bracket — reuses the same "risk-scope, then diversify"
idea as the stock/MF selector, but with round-robin instead of correlation
dedup (FD rates aren't a return series correlation applies to).
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import yaml
from sqlalchemy import select

from backend.config import get_config, repo_path
from backend.db import bank_pick_history, get_engine
from backend.selection.universe_selector import _risk_band_name

RECENCY_WINDOW = 5  # last N picks per risk bracket considered for the penalty


def _load_banks() -> list[dict]:
    cfg = get_config()
    with open(repo_path(cfg.download.bank_universe_file), encoding="utf-8") as f:
        return yaml.safe_load(f)["banks"]


def _band_name(risk_thermometer: float) -> str:
    bands = get_config().selection.risk_bands.to_dict()
    return _risk_band_name(risk_thermometer, bands)


def _scope_by_band(banks: list[dict], band_name: str) -> list[dict]:
    # Conservative users are scoped to major banks only; moderate/aggressive
    # users are also eligible for higher-rate small-finance banks.
    if band_name == "conservative":
        return [b for b in banks if b["tier"] == "major"]
    return banks


def _recent_pick_counts(band_name: str, n: int = RECENCY_WINDOW) -> dict[str, int]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            select(bank_pick_history.c.bank_id)
            .where(bank_pick_history.c.risk_bracket == band_name)
            .order_by(bank_pick_history.c.picked_at.desc())
            .limit(n)
        ).fetchall()
    counts: dict[str, int] = {}
    for (bank_id,) in rows:
        counts[bank_id] = counts.get(bank_id, 0) + 1
    return counts


def select_banks(risk_thermometer: float, n_banks: int, rng: np.random.Generator | None = None,
                  record_pick: bool = True) -> list[dict]:
    """Returns up to n_banks bank records (highest-rate eligible banks first,
    with the top-3 shuffled by recency-weighted round-robin so the same bank
    doesn't always land as the top pick)."""
    band_name = _band_name(risk_thermometer)
    eligible = sorted(_scope_by_band(_load_banks(), band_name), key=lambda b: b["rate_pct"], reverse=True)
    if not eligible:
        return []

    top_k = eligible[:3]
    rest = eligible[3:]

    recent_counts = _recent_pick_counts(band_name)
    weights = np.array([1.0 / (1 + recent_counts.get(b["id"], 0)) for b in top_k], dtype=float)
    weights = weights / weights.sum()

    rng = rng or np.random.default_rng()
    order = rng.choice(len(top_k), size=len(top_k), replace=False, p=weights)
    shuffled_top = [top_k[i] for i in order]

    picks = (shuffled_top + rest)[:n_banks]

    if record_pick and picks:
        now = datetime.now()
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(bank_pick_history.insert(), [
                {"risk_bracket": band_name, "bank_id": b["id"], "picked_at": now} for b in picks
            ])

    return picks
