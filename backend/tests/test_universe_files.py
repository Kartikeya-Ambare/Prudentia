import yaml

from backend.config import repo_path


def test_stock_universe_shape():
    data = yaml.safe_load(repo_path("universe", "stock_universe.yaml").read_text(encoding="utf-8"))
    assert len(data["sectors"]) == 12
    total = sum(len(s["tickers"]) for s in data["sectors"].values())
    assert 190 <= total <= 210
    for sector in data["sectors"].values():
        assert sector["display_name"]
        assert all(t.endswith(".NS") for t in sector["tickers"])


def test_mf_universe_shape():
    data = yaml.safe_load(repo_path("universe", "mf_universe.yaml").read_text(encoding="utf-8"))
    assert set(data["categories"]) == {"large_cap", "mid_cap", "small_cap"}
    assert data["max_schemes_per_category"] == 80
    for cat in data["categories"].values():
        assert len(cat["seed_schemes"]) >= 25


def test_bank_universe_shape():
    data = yaml.safe_load(repo_path("universe", "bank_universe.yaml").read_text(encoding="utf-8"))
    banks = data["banks"]
    assert len(banks) >= 12
    assert {b["tier"] for b in banks} <= {"major", "small_finance"}
    ids = [b["id"] for b in banks]
    assert len(ids) == len(set(ids))  # no duplicate bank ids
