"""HttpEngine: talks to the Prudentia backend over HTTP (httpx). No backend code is imported."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

import httpx

from chat_service.engine.client import (
    AllocationResult, EngineError, EngineRejected, EngineUnavailable, resolve_fund_name,
)

_LABEL_TO_BUCKET = {"Stocks": "stock", "Mutual Funds": "mf", "Bank/FD": "bank", "FD": "bank"}


class HttpEngine:
    def __init__(self, base_url: str, timeout: float = 15.0, client: Optional[httpx.Client] = None):
        self.base_url = base_url.rstrip("/")
        self.http = client or httpx.Client(timeout=timeout)

    # ---- transport ------------------------------------------------------------------
    def _req(self, method: str, path: str, *, ok404: bool = False, **kw: Any) -> Any:
        url = self.base_url + path
        try:
            r = self.http.request(method, url, **kw)
        except httpx.HTTPError as exc:
            raise EngineUnavailable(f"Allocation engine unreachable at {self.base_url}: {exc.__class__.__name__}") from exc
        if r.status_code == 404 and ok404:
            return None
        if r.status_code >= 400:
            if 400 <= r.status_code < 500:                      # a refusal with a reason (e.g. 422 validation)
                raise EngineRejected(f"Engine {method} {path} -> HTTP {r.status_code}", self._detail(r))
            raise EngineError(f"Engine {method} {path} -> HTTP {r.status_code}")
        try:
            return r.json()
        except ValueError as exc:
            raise EngineError(f"Engine {method} {path} returned non-JSON") from exc

    @staticmethod
    def _detail(r: httpx.Response) -> str:
        try:
            d = r.json().get("detail", "")
        except (ValueError, AttributeError):
            return ""
        if isinstance(d, list):                                 # pydantic: [{loc, msg, ...}]
            return "; ".join(f"{'.'.join(str(x) for x in e.get('loc', [])[1:])}: {e.get('msg', '')}" for e in d)
        return str(d)

    # ---- EngineClient (plan API: POST /plan, GET|PATCH /plan/{id}, POST /plan/{id}/rebalance, GET /banks) -------
    @staticmethod
    def _plan_body(req: dict) -> dict:
        """Chat-side keys -> backend PlanRequest/PlanPatch keys. Only keys present in `req` are sent."""
        m = {"amount": "capital", "risk_score": "risk_thermometer", "classes": "classes", "sector_pref": "sector_pref",
             "mf_category_pref": "mf_category_pref", "banks": "banks", "manual_split": "manual_split",
             "profile_id": "profile_id"}
        body = {m[k]: v for k, v in req.items() if k in m}
        if "years" in req:
            body["horizon_years"] = int(Decimal(str(req["years"])).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return body

    def allocate(self, request: dict) -> AllocationResult:
        data = self._req("POST", "/plan", json=self._plan_body(request))
        return self._from_backend(data)

    def update_plan(self, profile_id: str, patch: dict) -> dict:
        out = self._req("PATCH", f"/plan/{profile_id}", json=self._plan_body(patch))
        return {**out, "allocation": self._from_backend(out["allocation"])}

    def get_allocation(self, profile_id: str) -> Optional[dict]:
        alloc = self._req("GET", f"/plan/{profile_id}", ok404=True)
        if alloc is None:
            return None
        return {"allocation_json": self._from_backend(alloc), "explanation_text": alloc.get("explanation_text", "")}

    def rebalance(self, profile_id, from_bucket, to_bucket, pct=None, amount=None) -> dict:
        body = {"from": from_bucket, "to": to_bucket}
        body["pct" if pct is not None else "amount"] = pct if pct is not None else amount
        out = self._req("POST", f"/plan/{profile_id}/rebalance", json=body)
        return {**out, "allocation": self._from_backend(out["allocation"])}

    def list_banks(self) -> list[dict]:
        return self._req("GET", "/banks") or []

    def check_drift(self, profile_id: str) -> dict:
        data = self._req("GET", f"/rebalance-check/{profile_id}", ok404=True)
        return data if data is not None else {"found": False, "drifted": False,
                                              "message": "No saved allocation for this profile_id."}

    def known_fund_names(self) -> list[str]:
        rows = self._req("GET", "/mutual-funds") or []
        return [r.get("fund_name", "") for r in rows if r.get("fund_name")]

    def get_sector_history(self, fund_name: str) -> Optional[list]:
        name = resolve_fund_name(fund_name, self.known_fund_names()) or fund_name
        rows = self._req("GET", f"/mutual-funds/{name}/sector-history", ok404=True)
        return None if rows is None else [{"date": str(r.get("date", "")), "sector_json": r["sector_json"]} for r in rows]

    def get_sector_allocation(self, fund_name: str) -> Optional[dict]:
        name = resolve_fund_name(fund_name, self.known_fund_names()) or fund_name
        row = self._req("GET", f"/mutual-funds/{name}/sector-allocation", ok404=True)
        if row is None:
            return None
        return {"fund_name": name, "sector_json": row["sector_json"], "date": str(row.get("date", "")),
                "source_url": row.get("source_url", "")}

    # ---- adapter: backend plan (AllocationExplanation + plan fields) -> AllocationResult ---------------------
    @staticmethod
    def _from_backend(data: dict) -> AllocationResult:
        plan = data.get("plan_request") or {}
        total = sum(bp["present_value"] for bp in data["bucket_projections"])
        total = float(plan.get("capital") or total)
        split = data.get("split_pct")
        buckets = {b: {"weight_pct": 0.0, "amount": 0.0} for b in ("stock", "mf", "bank")}
        for bp in data["bucket_projections"]:
            b = _LABEL_TO_BUCKET.get(bp["label"])
            if b:
                pct = split[b] if split else 100 * bp["present_value"] / total if total else 0.0
                buckets[b] = {"weight_pct": round(pct, 1), "amount": round(bp["present_value"], 2)}
        proj = {p["label"]: p["projected_value"] for p in data.get("instrument_projections", [])}
        out: AllocationResult = {
            "profile_id": data["profile_id"], "amount": total, "years": data["horizon_years"],
            "risk_score": data["risk_thermometer"],
            "classes": list(data.get("classes") or ["stocks", "mf", "fd"]),
            "buckets": buckets,
            "instruments": [{"label": w["label"], "display_name": w["display_name"], "bucket": w["bucket"],
                             "weight_pct": round(w["weight_pct"], 2), "amount": round(w["amount"], 2),
                             **({"projected_value": round(proj[w["display_name"]])} if w["display_name"] in proj else {})}
                            for w in data["weights"]],
            "expected_return_pct": data.get("expected_return_pct"),
            "data_as_of": data.get("data_as_of") or {}, "warnings": list(data.get("warnings", [])),
            "requires_confirmation": bool(data.get("requires_confirmation", False)),
            "explanation_text": data.get("explanation_text", ""),
            "sector_pref": list(plan.get("sector_pref") or []), "mf_category_pref": list(plan.get("mf_category_pref") or []),
            "banks": plan.get("banks", "auto"), "banks_mode": data.get("banks_mode", "auto"),
            "backend": data,                                   # the backend's own plan, for the UI
        }
        if split:
            out["split_pct"] = dict(split)
        if plan.get("manual_split"):
            out["manual_split"] = dict(plan["manual_split"])
        if data.get("scenarios"):
            out["scenarios"] = data["scenarios"]
        return out
