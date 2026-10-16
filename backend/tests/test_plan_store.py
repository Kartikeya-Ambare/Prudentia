"""Stored-plan helpers: bucket split, total capital and drift checking, against a hand-made stored plan."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine

from backend import plan_store
from backend.db import metadata, profile_allocations

SAMPLE_ALLOCATION = {
    "profile_id": "p1", "mode": "naive", "risk_thermometer": 50.0, "horizon_years": 5,
    "weights": [], "expected_return_pct": 10.0, "expected_volatility_pct": 12.0,
    "explanation_text": "summary text",
    "bucket_projections": [
        {"label": "Stocks", "present_value": 40000.0, "projected_value": 60000.0,
         "projected_return_pct": 8.4, "horizon_years": 5},
        {"label": "Mutual Funds", "present_value": 40000.0, "projected_value": 55000.0,
         "projected_return_pct": 6.6, "horizon_years": 5},
        {"label": "Bank/FD", "present_value": 20000.0, "projected_value": 26000.0,
         "projected_return_pct": 5.4, "horizon_years": 5},
    ],
    "instrument_projections": [], "banks_selected": [],
}


@pytest.fixture
def stored_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(profile_allocations.insert().values(
            profile_id="p1", mode="naive", risk_thermometer=50.0, horizon_years=5,
            allocation_json=SAMPLE_ALLOCATION, updated_at=datetime.now(),
        ))
    monkeypatch.setattr(plan_store, "get_engine", lambda: engine)
    return engine


def test_bucket_split_from_allocation_sums_to_one():
    split = plan_store._bucket_split_from_allocation(SAMPLE_ALLOCATION)
    assert split == {"stock": pytest.approx(0.4), "mf": pytest.approx(0.4), "bank": pytest.approx(0.2)}


def test_total_capital():
    assert plan_store._total_capital(SAMPLE_ALLOCATION) == 100000.0


def test_check_drift_reports_no_drift_when_recompute_matches(stored_db, monkeypatch):
    def fake_allocate(profile, bucket_split_override=None):
        from shared.schemas.models import AllocationExplanation
        return AllocationExplanation(**SAMPLE_ALLOCATION)
    monkeypatch.setattr(plan_store, "allocate", fake_allocate)

    result = plan_store.check_drift("p1")
    assert result["found"] is True
    assert result["drifted"] is False


def test_check_drift_detects_material_drift(stored_db, monkeypatch):
    def fake_allocate(profile, bucket_split_override=None):
        from shared.schemas.models import AllocationExplanation
        drifted = {**SAMPLE_ALLOCATION, "bucket_projections": [
            {**SAMPLE_ALLOCATION["bucket_projections"][0], "present_value": 55000.0},  # stocks rallied hard
            SAMPLE_ALLOCATION["bucket_projections"][1],
            SAMPLE_ALLOCATION["bucket_projections"][2],
        ]}
        return AllocationExplanation(**drifted)
    monkeypatch.setattr(plan_store, "allocate", fake_allocate)

    result = plan_store.check_drift("p1")
    assert result["found"] is True
    assert result["drifted"] is True


def test_check_drift_unknown_profile(stored_db):
    result = plan_store.check_drift("nope")
    assert result["found"] is False
