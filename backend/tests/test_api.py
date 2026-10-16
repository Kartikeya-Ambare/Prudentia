from fastapi.testclient import TestClient

from backend.api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_mutual_funds_list_is_empty_list_when_no_scrapes_yet():
    r = client.get("/mutual-funds")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_sector_allocation_404_for_unknown_fund():
    r = client.get("/mutual-funds/Totally Made Up Fund Name/sector-allocation")
    assert r.status_code == 404
