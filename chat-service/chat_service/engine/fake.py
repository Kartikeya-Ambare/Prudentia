"""FakeEngine: deterministic, in-memory stand-in for the Prudentia backend (tests, demo, front-end dev).

Numbers are illustrative fixtures, not financial output. Same shapes as the real engine (client.py)."""
from __future__ import annotations

import copy
import math
import uuid
from typing import Optional

from chat_service.engine.client import AllocationResult, EngineError, EngineRejected, resolve_fund_name

BUCKET_OF_CLASS = {"stocks": "stock", "mf": "mf", "fd": "bank"}
BUCKET_LABEL = {"stock": "Stocks", "mf": "Mutual Funds", "bank": "FD"}
_RETURN = {"stock": 12.0, "mf": 10.5, "bank": 7.0}
_VOL = {"stock": 18.0, "mf": 14.0, "bank": 1.0}
_INSTRUMENTS = {
    "stock": [("HDFCBANK", "HDFC Bank"), ("TCS", "Tata Consultancy Services")],
    "mf": [("HDFC-LC", "HDFC Large Cap Fund"), ("SBI-SC", "SBI Small Cap Fund")],
    "bank": [("SBI-FD", "SBI Fixed Deposit"), ("HDFC-FD", "HDFC Bank Fixed Deposit")],
}
DATA_AS_OF = "2026-10-01"
FAKE_BANKS = [
    {"id": "equitas_sfb", "display_name": "Equitas Small Finance Bank", "tier": "small_finance", "category": "private", "rate_pct": 8.5},
    {"id": "idfcfirstb", "display_name": "IDFC First Bank", "tier": "major", "category": "private", "rate_pct": 7.5},
    {"id": "axisbank", "display_name": "Axis Bank", "tier": "major", "category": "private", "rate_pct": 7.1},
    {"id": "hdfcbank", "display_name": "HDFC Bank", "tier": "major", "category": "private", "rate_pct": 7.0},
    {"id": "icicibank", "display_name": "ICICI Bank", "tier": "major", "category": "private", "rate_pct": 7.0},
    {"id": "kotakbank", "display_name": "Kotak Mahindra Bank", "tier": "major", "category": "private", "rate_pct": 7.0},
    {"id": "sbin", "display_name": "State Bank of India", "tier": "major", "category": "public", "rate_pct": 6.8},
    {"id": "pnb", "display_name": "Punjab National Bank", "tier": "major", "category": "public", "rate_pct": 6.8},
    {"id": "canbk", "display_name": "Canara Bank", "tier": "major", "category": "public", "rate_pct": 6.8},
    {"id": "unionbank", "display_name": "Union Bank of India", "tier": "major", "category": "public", "rate_pct": 6.8},
]
_ALL = ["stocks", "mf", "fd"]
_STOCKS_BY_SECTOR = {
    "banking": [("HDFCBANK", "HDFC Bank"), ("ICICIBANK", "ICICI Bank")],
    "it_technology": [("TCS", "Tata Consultancy Services"), ("INFY", "Infosys")],
    "pharma_healthcare": [("SUNPHARMA", "Sun Pharma")], "fmcg": [("ITC", "ITC")],
    "energy_power": [("RELIANCE", "Reliance Industries")], "metals_mining": [("TATASTEEL", "Tata Steel")],
    "auto_ancillary": [("BOSCHLTD", "Bosch")],
}
_MF_BY_CATEGORY = {"Large Cap": ("HDFC-LC", "HDFC Large Cap Fund"), "Mid Cap": ("KOTAK-EE", "Kotak Emerging Equity Fund"),
                   "Small Cap": ("SBI-SC", "SBI Small Cap Fund")}
SECTOR_HISTORY = {
    "HDFC Large Cap Fund": [("2026-09-01", {"Financial Services": 33.1, "Information Technology": 11.0, "Energy": 8.7,
                                            "Consumer Goods": 8.2, "Healthcare": 6.0, "Automobile": 6.4, "Others": 26.6}),
                            ("2026-10-01", None)],
    "SBI Small Cap Fund": [("2026-09-01", {"Industrials": 20.5, "Consumer Discretionary": 16.9, "Financial Services": 13.0,
                                           "Materials": 12.8, "Healthcare": 9.0, "Information Technology": 7.3, "Others": 20.5}),
                           ("2026-10-01", None)],
}

SECTORS = {
    "HDFC Large Cap Fund": {"Financial Services": 34.5, "Information Technology": 10.2, "Energy": 9.1,
                            "Consumer Goods": 8.0, "Healthcare": 6.5, "Automobile": 6.0, "Others": 25.7},
    "SBI Small Cap Fund": {"Industrials": 22.0, "Consumer Discretionary": 16.3, "Financial Services": 14.2,
                           "Materials": 12.0, "Healthcare": 9.5, "Information Technology": 7.0, "Others": 19.0},
}


SECTOR_HISTORY = {k: [(d, v if v is not None else SECTORS[k]) for d, v in rows] for k, rows in SECTOR_HISTORY.items()}


def _round_to_100(vals: dict[str, float]) -> dict[str, int]:
    """Largest-remainder rounding so integer percentages sum to exactly 100."""
    floors = {k: math.floor(v) for k, v in vals.items()}
    left = 100 - sum(floors.values())
    for k in sorted(vals, key=lambda k: vals[k] - floors[k], reverse=True)[:left]:
        floors[k] += 1
    return floors


def _split_for(risk_score: float, years: float, classes: list[str]) -> dict[str, float]:
    r = risk_score / 100.0
    stock = 0.10 + 0.60 * r
    mf = 0.35
    fd = 1.0 - stock - mf
    shift = max(-0.15, min(0.15, 0.02 * (years - 5)))     # longer horizon -> more equity
    stock, fd = stock + shift, fd - shift
    raw = {"stock": max(stock, 0.0), "mf": mf, "bank": max(fd, 0.05)}
    keep = {BUCKET_OF_CLASS[c] for c in classes}
    raw = {b: (v if b in keep else 0.0) for b, v in raw.items()}
    tot = sum(raw.values()) or 1.0
    return {b: v / tot * 100 for b, v in raw.items()}


class FakeEngine:
    def __init__(self) -> None:
        self._store: dict[str, AllocationResult] = {}
        self._store["demo"] = self._build("demo", 500000, 5, 50, ["stocks", "mf", "fd"])
        self._store["demo-drift"] = self._build("demo-drift", 1000000, 5, 50, ["stocks", "mf", "fd"])
        # a profile whose stored split has drifted from what the engine would recompute today
        self._drift = {"demo-drift": [
            {"bucket": "Stocks", "before": 400000.0, "after": 460000.0, "delta": 60000.0},
            {"bucket": "Mutual Funds", "before": 350000.0, "after": 340000.0, "delta": -10000.0},
            {"bucket": "FD", "before": 250000.0, "after": 200000.0, "delta": -50000.0},
        ]}

    # ---- core builder -------------------------------------------------------------------
    def _build(self, profile_id: str, amount: float, years: float, risk: float, classes: list[str],
               split: Optional[dict[str, float]] = None, sector_pref: Optional[list] = None,
               mf_category_pref: Optional[list] = None, banks="auto") -> AllocationResult:
        sector_pref, mf_category_pref = list(sector_pref or []), list(mf_category_pref or [])
        inst_map = dict(_INSTRUMENTS)
        if banks != "auto":
            by_id = {b["id"]: b for b in FAKE_BANKS}
            inst_map["bank"] = [(i, by_id[i]["display_name"]) for i in banks]
        if sector_pref:
            stocks = []
            for sec in sector_pref:
                stocks += _STOCKS_BY_SECTOR.get(sec, [("GEN-" + sec.upper()[:6], sec.replace("_", " ").title() + " Basket")])
            inst_map["stock"] = stocks[:4]
        if mf_category_pref:
            inst_map["mf"] = [_MF_BY_CATEGORY[c] for c in mf_category_pref if c in _MF_BY_CATEGORY]
        pct = _round_to_100(split or _split_for(risk, years, classes))
        if split:                                              # a manual / rebalanced split decides the classes
            classes = [c for c in _ALL if pct[BUCKET_OF_CLASS[c]] > 0]
        buckets = {b: {"weight_pct": pct[b], "amount": round(amount * pct[b] / 100.0, 2)} for b in pct}
        instruments = []
        for b, items in inst_map.items():
            if pct[b] == 0:
                continue
            for label, name in items:
                w = pct[b] / len(items)
                amt = round(amount * w / 100.0, 2)
                instruments.append({"label": label, "display_name": name, "bucket": b,
                                    "weight_pct": round(w, 2), "amount": amt,
                                    "projected_value": round(amt * (1 + _RETURN[b] / 100.0) ** years, 0)})
        er = sum(_RETURN[b] * pct[b] for b in pct) / 100.0
        vol = 0.9 * sum(_VOL[b] * pct[b] for b in pct) / 100.0
        spread = 1.645 * vol / math.sqrt(max(years, 1))
        p5, p95 = er - spread, er + spread

        def proj(rate: float) -> float:
            return round(amount * (1 + rate / 100.0) ** years, 0)

        warnings: list[str] = []
        confirm = False
        if risk >= 80 and years <= 2:
            warnings.append("High risk with a horizon of only 1 to 2 years means stocks can lose money in the short term.")
            confirm = True
        if classes == ["fd"] and risk >= 80:
            warnings.append("High risk makes no difference with FD only, so the allocation stays FD only.")
            confirm = True
        if classes == ["stocks"] and years < 3:
            warnings.append("Stocks only for under 3 years can be very volatile.")
            confirm = True
        scenarios = None
        if pct["stock"] or pct["mf"]:
            scenarios = {k: {"projected_value": proj(r), "return_pct": round(r, 1)}
                         for k, r in (("bear", p5), ("base", er), ("bull", p95))}
        return {
            "profile_id": profile_id, "amount": float(amount), "years": years, "risk_score": risk,
            "classes": list(classes), "buckets": buckets, "instruments": instruments,
            "split_pct": {b: float(v) for b, v in pct.items()}, "scenarios": scenarios,
            "banks": banks if banks == "auto" else list(banks), "banks_mode": "auto" if banks == "auto" else "custom",
            "sector_pref": sector_pref, "mf_category_pref": mf_category_pref,
            "expected_return_pct": round(er, 1), "p5_return_pct": round(p5, 1), "p95_return_pct": round(p95, 1),
            "projected": {"p5": proj(p5), "expected": proj(er), "p95": proj(p95)},
            "data_as_of": {"stocks": DATA_AS_OF, "mf": DATA_AS_OF}, "warnings": warnings, "requires_confirmation": confirm,
            "explanation_text": (
                f"With a risk score of {risk:g} and a {years:g}-year horizon, stocks are {pct['stock']}%, "
                f"mutual funds {pct['mf']}% and FD {pct['bank']}%. More risk and a longer horizon raise the stocks share; "
                "less risk raises the FD share."),
        }

    # ---- EngineClient --------------------------------------------------------------------
    @staticmethod
    def _validate(req: dict) -> None:
        """Same refusals as the backend's PlanRequest (HTTP 422 there)."""
        if float(req["amount"]) <= 0:
            raise EngineRejected("422", "capital: Input should be greater than 0")
        if not 1 <= float(req["years"]) <= 40:
            raise EngineRejected("422", "horizon_years: Input should be between 1 and 40")
        if not 0 <= float(req["risk_score"]) <= 100:
            raise EngineRejected("422", "risk_thermometer: Input should be between 0 and 100")
        if not req["classes"]:
            raise EngineRejected("422", "classes: List should have at least 1 item")
        banks = req.get("banks", "auto")
        if banks != "auto":
            known = {b["id"] for b in FAKE_BANKS}
            bad = [b for b in banks if b not in known]
            if bad:
                raise EngineRejected("422", f"unknown bank ids: {', '.join(bad)}")
            if not banks:
                raise EngineRejected("422", "banks must be 'auto' or a non-empty list of bank ids")

    def allocate(self, request: dict) -> AllocationResult:
        classes = list(request.get("classes") or _ALL)
        pid = request.get("profile_id") or f"chat-{uuid.uuid4().hex[:8]}"
        banks = request.get("banks", "auto")
        self._validate({**request, "classes": classes, "banks": banks})
        split = None
        if request.get("manual_split"):
            raw = {BUCKET_OF_CLASS[c]: float(v) for c, v in request["manual_split"].items()}
            split = {b: raw.get(b, 0.0) for b in ("stock", "mf", "bank")}
        res = self._build(pid, float(request["amount"]), float(request["years"]), float(request["risk_score"]), classes,
                          split=split, sector_pref=request.get("sector_pref"),
                          mf_category_pref=request.get("mf_category_pref"), banks=banks)
        res["manual_split"] = request.get("manual_split")
        self._store[pid] = res
        return copy.deepcopy(res)

    def update_plan(self, profile_id: str, patch: dict) -> dict:
        old = self._store.get(profile_id)
        if old is None:
            raise EngineError(f"unknown profile {profile_id}")
        req = {"amount": old["amount"], "years": old["years"], "risk_score": old["risk_score"],
               "classes": old["classes"], "sector_pref": old.get("sector_pref"),
               "mf_category_pref": old.get("mf_category_pref"), "banks": old.get("banks", "auto"),
               "manual_split": old.get("manual_split"), "profile_id": profile_id}
        for k, v in patch.items():
            if v is not None or k == "manual_split":
                req[k] = v
        if "classes" in patch and "manual_split" not in patch:
            req["manual_split"] = None                          # new class list -> back to the risk-based split
        new = self.allocate(req)
        diff = [{"bucket": BUCKET_LABEL[b], "before": old["buckets"][b]["amount"], "after": new["buckets"][b]["amount"],
                 "delta": round(new["buckets"][b]["amount"] - old["buckets"][b]["amount"], 2)} for b in new["buckets"]]
        return {"allocation": new, "diff": diff}

    def list_banks(self) -> list[dict]:
        return copy.deepcopy(FAKE_BANKS)

    def get_allocation(self, profile_id: str) -> Optional[dict]:
        res = self._store.get(profile_id)
        return None if res is None else {"allocation_json": copy.deepcopy(res), "explanation_text": res["explanation_text"]}

    def rebalance(self, profile_id, from_bucket, to_bucket, pct=None, amount=None) -> dict:
        old = self._store.get(profile_id)
        if old is None:
            raise EngineError(f"unknown profile {profile_id}")
        total = old["amount"]
        if old["buckets"][from_bucket]["weight_pct"] <= 0:
            raise EngineRejected("422", "There is no money in that class to move.")
        requested = total * pct / 100.0 if pct is not None else float(amount or 0.0)
        split = {b: float(old["buckets"][b]["weight_pct"]) for b in old["buckets"]}
        available_amt = total * split[from_bucket] / 100.0
        moved_amt = min(available_amt, requested)
        moved_pct = moved_amt / total * 100.0 if total else 0.0
        new_split = dict(split)
        new_split[from_bucket] -= moved_pct
        new_split[to_bucket] += moved_pct
        new = self._build(profile_id, total, old["years"], old["risk_score"], old["classes"], new_split,
                          old.get("sector_pref"), old.get("mf_category_pref"), old.get("banks", "auto"))
        new["manual_split"] = {c: round(new["split_pct"][BUCKET_OF_CLASS[c]], 2) for c in new["classes"]}
        diff = [{"bucket": BUCKET_LABEL[b], "before": old["buckets"][b]["amount"], "after": new["buckets"][b]["amount"],
                 "delta": round(new["buckets"][b]["amount"] - old["buckets"][b]["amount"], 2)} for b in new["buckets"]]
        self._store[profile_id] = new
        return {"allocation": copy.deepcopy(new), "diff": diff, "moved_amount": round(moved_amt, 2),
                "requested_amount": round(requested, 2), "capped": moved_amt < requested - 0.5}

    def check_drift(self, profile_id: str) -> dict:
        if profile_id not in self._store:
            return {"found": False, "drifted": False, "message": "No saved allocation for this profile_id."}
        diff = self._drift.get(profile_id)
        if diff is None:
            res = self._store[profile_id]
            diff = [{"bucket": BUCKET_LABEL[b], "before": v["amount"], "after": v["amount"], "delta": 0.0}
                    for b, v in res["buckets"].items()]
        total = sum(d["before"] for d in diff)
        drifted = any(abs(d["delta"]) > 0.01 * total for d in diff)
        return {"found": True, "drifted": drifted, "diff": diff, "checked_at": DATA_AS_OF}

    def known_fund_names(self) -> list[str]:
        return list(SECTORS)

    def get_sector_history(self, fund_name: str) -> Optional[list]:
        name = resolve_fund_name(fund_name, self.known_fund_names())
        if name is None:
            return None
        return [{"date": d, "sector_json": dict(v)} for d, v in SECTOR_HISTORY[name]]

    def get_sector_allocation(self, fund_name: str) -> Optional[dict]:
        name = resolve_fund_name(fund_name, self.known_fund_names())
        if name is None:
            return None
        return {"fund_name": name, "sector_json": dict(SECTORS[name]), "date": DATA_AS_OF,
                "source_url": "https://example.invalid/fixtures/" + name.lower().replace(" ", "-")}
