from fastapi.testclient import TestClient

from backend.api.main import app

client = TestClient(app)
BASE = {"capital": 200000, "horizon_years": 5, "risk_thermometer": 50}


def _plan(**extra):
    r = client.post("/plan", json={**BASE, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _invested(d):
    return sum(b["present_value"] for b in d["bucket_projections"])


def test_default_plan_uses_all_classes_and_five_auto_banks():
    d = _plan()
    assert d["classes"] == ["stocks", "mf", "fd"]
    assert d["banks_mode"] == "auto" and len(d["banks_selected"]) == 5
    assert abs(sum(d["split_pct"].values()) - 100) < 0.1
    assert abs(_invested(d) - BASE["capital"]) <= BASE["capital"] * 0.01  # the engine may leave up to 1% unallocated


def test_plan_invests_the_full_amount_for_any_split():
    """The optimiser's cleaned weights used to add up to ~99.6%, leaving a few hundred rupees uninvested."""
    for extra in ({}, {"classes": ["stocks"]}, {"classes": ["stocks", "fd"], "manual_split": {"stocks": 70, "fd": 30}},
                  {"classes": ["stocks", "mf"], "manual_split": {"stocks": 64.7, "mf": 35.3}}, {"risk_thermometer": 80}):
        d = _plan(capital=500000, **extra)
        assert abs(_invested(d) - 500000) < 0.5, (extra, _invested(d))
        for bucket in ("stock", "mf"):
            held = sum(w["amount"] for w in d["weights"] if w["bucket"] == bucket)
            assert abs(held - 500000 * d["split_pct"][bucket] / 100) < 26   # split_pct is rounded to 0.01%


def test_scenarios_explain_a_narrow_optimistic_case():
    sc = _plan(capital=500000)["scenarios"]
    down = sc["base"]["projected_value"] - sc["bear"]["projected_value"]
    up = sc["bull"]["projected_value"] - sc["base"]["projected_value"]
    assert sc["bear"]["projected_value"] <= sc["base"]["projected_value"] <= sc["bull"]["projected_value"]
    assert ("note" in sc) == (down > 0 and up < 0.25 * down)       # a narrow upside always comes with the explanation


def test_only_chosen_classes_receive_money():
    d = _plan(classes=["fd"])
    assert d["split_pct"] == {"stock": 0.0, "mf": 0.0, "bank": 100.0}
    assert abs(_invested(d) - BASE["capital"]) <= BASE["capital"] * 0.01  # the engine may leave up to 1% unallocated


def test_chosen_banks_are_respected():
    ids = [b["id"] for b in client.get("/banks").json()][:2]   # whatever the bank universe currently holds
    d = _plan(classes=["stocks", "fd"], banks=ids)
    assert d["banks_mode"] == "custom" and len(d["banks_selected"]) == 2


def test_manual_split():
    d = _plan(classes=["stocks", "fd"], manual_split={"stocks": 70, "fd": 30})
    assert d["split_pct"]["stock"] == 70.0 and d["split_pct"]["bank"] == 30.0


def test_validation_errors():
    for bad in ({"banks": ["nope"]}, {"classes": []},
                {"classes": ["stocks", "fd"], "manual_split": {"stocks": 50, "fd": 10}}):
        assert client.post("/plan", json={**BASE, **bad}).status_code == 422
    assert client.get("/plan/does-not-exist").status_code == 404


def test_patch_changes_years_classes_and_capital():
    pid = _plan()["profile_id"]
    r = client.patch(f"/plan/{pid}", json={"horizon_years": 10}).json()
    assert r["allocation"]["horizon_years"] == 10
    r = client.patch(f"/plan/{pid}", json={"classes": ["stocks", "mf"]}).json()
    assert r["allocation"]["split_pct"]["bank"] == 0.0
    r = client.patch(f"/plan/{pid}", json={"capital": 400000}).json()
    assert abs(_invested(r["allocation"]) - 400000) <= 400000 * 0.01


def test_rebalance_can_add_a_class():
    pid = _plan(classes=["stocks", "fd"])["profile_id"]
    r = client.post(f"/plan/{pid}/rebalance", json={"from": "bank", "to": "mf", "pct": 5}).json()
    assert "mf" in r["allocation"]["classes"] and r["moved_amount"] > 0


def test_banks_and_data_status():
    banks = client.get("/banks").json()
    assert len(banks) >= 5
    assert set(client.get("/data-status").json()) >= {"stocks", "mf"}
