from fastapi.testclient import TestClient

from backend import plan_store
from backend.api.main import app

client = TestClient(app)


def test_rebalance_check_404_for_unknown_profile():
    assert client.get("/rebalance-check/does-not-exist").status_code == 404


def test_rebalance_check_returns_the_drift_result(monkeypatch):
    monkeypatch.setattr(plan_store, "check_drift", lambda pid: {"found": True, "drifted": False, "diff": []})
    resp = client.get("/rebalance-check/p1")
    assert resp.status_code == 200
    assert resp.json()["found"] is True
