"""Integration smoke test for orchestrator.allocate() — runs against
whatever's currently in the dev DB (download.py's --limit 2 smoke test
populated HDFCBANK.NS / ICICIBANK.NS and two MF schemes). This intentionally
exercises the real selection -> forecast -> tax -> optimize -> projection
pipeline end-to-end rather than mocking each stage, since M0-M6 already have
their own isolated unit tests.
"""
import pytest

from backend.data.cache_manager import get_prices
from backend.orchestrator import allocate
from shared.schemas.models import UserProfile

pytestmark = pytest.mark.skipif(
    get_prices("HDFCBANK.NS").empty,
    reason="requires `python download.py --limit 2` to have been run first",
)


@pytest.mark.parametrize("risk", [10, 50, 90])
def test_allocate_produces_valid_explanation(risk):
    profile = UserProfile(mode="naive", capital=100_000, risk_thermometer=risk, horizon_years=5)
    result = allocate(profile)

    assert result.profile_id
    assert result.mode == "naive"
    assert len(result.bucket_projections) == 3
    assert {bp.label for bp in result.bucket_projections} == {"Stocks", "Mutual Funds", "Bank/FD"}

    total_weighted_amount = sum(w.amount for w in result.weights)
    assert total_weighted_amount == pytest.approx(100_000, rel=0.02)

    for bucket_label in ("stock", "mf", "bank"):
        bucket_weights = [w for w in result.weights if w.bucket == bucket_label]
        if bucket_weights:
            assert sum(w.weight_pct for w in bucket_weights) == pytest.approx(100, abs=1)


def test_higher_risk_shifts_capital_toward_equity():
    conservative = allocate(UserProfile(mode="naive", capital=100_000, risk_thermometer=5, horizon_years=5))
    aggressive = allocate(UserProfile(mode="naive", capital=100_000, risk_thermometer=95, horizon_years=5))

    def stock_amount(result):
        return sum(w.amount for w in result.weights if w.bucket == "stock")

    assert stock_amount(aggressive) > stock_amount(conservative)


def test_knowledgeable_mode_sector_pref_is_honored():
    import yaml
    from backend.config import get_config, repo_path

    universe = yaml.safe_load(repo_path(get_config().download.universe_file).read_text(encoding="utf-8"))
    banking_tickers = set(universe["sectors"]["banking"]["tickers"])

    profile = UserProfile(
        mode="knowledgeable", capital=100_000, risk_thermometer=50, horizon_years=5,
        sector_pref=["Banking"],
    )
    result = allocate(profile)
    stock_labels = {w.label for w in result.weights if w.bucket == "stock"}
    assert stock_labels, "expected at least one Banking-sector stock to be selected"
    assert stock_labels.issubset(banking_tickers)
