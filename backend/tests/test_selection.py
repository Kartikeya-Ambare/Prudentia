from collections import Counter

import numpy as np
import pandas as pd
import pytest
import yaml
from sqlalchemy import create_engine

from backend.config import get_config, repo_path
from backend.db import metadata
from backend.selection import bank_selector, universe_selector


def _price_df(seed: int, n: int = 300, drift: float = 0.0004, vol: float = 0.015) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(drift, vol, n)
    prices = 100 * np.exp(np.cumsum(log_returns))
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    return pd.DataFrame({"adj_close": prices}, index=dates)


@pytest.fixture
def fake_prices(monkeypatch):
    def _get_prices(ticker, force_refresh=False):
        return _price_df(seed=abs(hash(ticker)) % 10_000)
    monkeypatch.setattr(universe_selector, "get_prices", _get_prices)


def test_sector_pref_scopes_candidates_to_that_sector(fake_prices):
    banking_only = universe_selector.select_stock_candidates(risk_thermometer=50, sector_pref=["Banking"])
    universe = yaml.safe_load(repo_path(get_config().download.universe_file).read_text(encoding="utf-8"))
    banking_tickers = set(universe["sectors"]["banking"]["tickers"])
    assert set(banking_only).issubset(banking_tickers)
    assert len(banking_only) > 0


def test_candidate_pool_is_capped(fake_prices):
    candidates = universe_selector.select_stock_candidates(risk_thermometer=80)
    assert len(candidates) <= get_config().selection.candidate_pool_size


def test_zero_price_rows_do_not_produce_inf_or_nan_volatility():
    # Regression test: some sources contain literal 0.0 price/NAV rows
    # (not NaN), which used to poison np.log() with -inf.
    df = _price_df(seed=1)
    df.loc[df.index[10], "adj_close"] = 0.0
    vol = universe_selector._annualized_volatility(df["adj_close"])
    assert vol is not None and np.isfinite(vol)
    sharpe = universe_selector._sharpe(df["adj_close"])
    assert np.isfinite(sharpe)


@pytest.fixture
def isolated_bank_db(monkeypatch):
    test_engine = create_engine("sqlite:///:memory:")
    metadata.create_all(test_engine)
    monkeypatch.setattr(bank_selector, "get_engine", lambda: test_engine)
    return test_engine


def test_conservative_band_scopes_to_major_tier_only(isolated_bank_db):
    banks = bank_selector.select_banks(risk_thermometer=10, n_banks=20, record_pick=False)
    assert all(b["tier"] == "major" for b in banks)


def test_top_pick_diversifies_over_repeated_calls(isolated_bank_db):
    rng = np.random.default_rng(0)
    top_picks = [bank_selector.select_banks(risk_thermometer=20, n_banks=3, rng=rng)[0]["id"] for _ in range(20)]
    assert len(set(top_picks)) >= 2, f"top pick never varied: {Counter(top_picks)}"
