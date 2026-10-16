"""Plan endpoints for the redesigned frontend (additive: no existing route, schema or core function changes).

A "plan" is a normal allocation plus the choices the three user modes need and /allocate cannot express:

  classes       which of stocks / mf / fd get money (only the chosen ones are funded)
  banks         "auto" (best 5 for the risk band) or a list of bank ids from GET /banks
  manual_split  optional exact percentages per chosen class (else the risk-based split, rescaled)

It reuses the engine as-is: `allocate()` does the stock and mutual fund legs (called with a split that
funds only the chosen equity classes); the FD leg is built here with the same helpers `allocate()` uses
(`select_banks`, `post_tax_return`, `instrument_projection`). Plans are stored through the existing
`profile_allocations` table, so the existing /rebalance-check and chat endpoints keep working on them.

  POST  /plan                         create a plan
  GET   /plan/{profile_id}            the stored plan
  PATCH /plan/{profile_id}            change any inputs (years, amount, risk, classes, banks, ...) and recompute
  POST  /plan/{profile_id}/rebalance  shift part of one class into another (keeps the other choices)
  GET   /banks                        the bank list a user can pick from
  GET   /data-status                  how fresh the price data is
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select

from backend.plan_store import _build_diff, _load_stored_profile
from backend.config import repo_path
from backend.db import get_engine, mf_nav, prices
from backend.forecasting.fundamentals_formatter import bucket_projection, instrument_projection
from backend.forecasting.tax_engine import post_tax_return
from backend.orchestrator import _bucket_split, _persist_profile_allocation, allocate
from backend.selection.bank_selector import _load_banks, select_banks
from shared.schemas.models import AllocationExplanation, InstrumentWeight, UserProfile

router = APIRouter()

AssetClass = Literal["stocks", "mf", "fd"]
_BUCKET_OF = {"stocks": "stock", "mf": "mf", "fd": "bank"}
_BUCKETS = ("stock", "mf", "bank")
_ALL_CLASSES: list[str] = ["stocks", "mf", "fd"]
AUTO_BANK_COUNT = 5
DEPOSIT_INSURANCE_LIMIT = 500_000   # DICGC cover per depositor per bank, in rupees
STALE_AFTER_DAYS = 5


# ----------------------------------------------------------------------------- models
class PlanRequest(BaseModel):
    profile_id: Optional[str] = None
    capital: float = Field(gt=0)
    horizon_years: int = Field(ge=1, le=40)
    risk_thermometer: float = Field(ge=0, le=100)          # the risk % the user can afford, 0 to 100
    classes: list[AssetClass] = Field(default_factory=lambda: list(_ALL_CLASSES), min_length=1)
    sector_pref: list[str] = Field(default_factory=list)
    mf_category_pref: list[Literal["Large Cap", "Mid Cap", "Small Cap"]] = Field(default_factory=list)
    banks: Literal["auto"] | list[str] = "auto"
    manual_split: Optional[dict[AssetClass, float]] = None  # percent per chosen class, must sum to 100

    @field_validator("classes")
    @classmethod
    def _unique_classes(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def _check_choices(self) -> "PlanRequest":
        if self.manual_split is not None:
            if set(self.manual_split) != set(self.classes):
                raise ValueError("manual_split must have exactly one percentage for each chosen class")
            if any(p < 0 for p in self.manual_split.values()) or abs(sum(self.manual_split.values()) - 100) > 0.5:
                raise ValueError("manual_split percentages must be non-negative and add up to 100")
        if isinstance(self.banks, list):
            known = {b["id"] for b in _load_banks()}
            unknown = [b for b in self.banks if b not in known]
            if unknown:
                raise ValueError(f"unknown bank ids: {', '.join(unknown)}")
            if not self.banks:
                raise ValueError("banks must be 'auto' or a non-empty list of bank ids")
        return self


class PlanPatch(BaseModel):
    """Every field optional; only the fields sent are changed. Send banks: "auto" to go back to automatic
    banks, and manual_split: null to go back to the risk-based split."""
    capital: Optional[float] = Field(default=None, gt=0)
    horizon_years: Optional[int] = Field(default=None, ge=1, le=40)
    risk_thermometer: Optional[float] = Field(default=None, ge=0, le=100)
    classes: Optional[list[AssetClass]] = Field(default=None, min_length=1)
    sector_pref: Optional[list[str]] = None
    mf_category_pref: Optional[list[Literal["Large Cap", "Mid Cap", "Small Cap"]]] = None
    banks: Optional[Literal["auto"] | list[str]] = None
    manual_split: Optional[dict[AssetClass, float]] = None


class PlanRebalance(BaseModel):
    from_bucket: str = Field(alias="from", pattern="^(stock|mf|bank)$")
    to_bucket: str = Field(alias="to", pattern="^(stock|mf|bank)$")
    pct: Optional[float] = Field(default=None, gt=0, le=100)
    amount: Optional[float] = Field(default=None, gt=0)
    model_config = {"populate_by_name": True}


class PlanResult(AllocationExplanation):
    """AllocationExplanation plus the plan choices. Extra fields are stored with the allocation."""
    classes: list[str]
    split_pct: dict[str, float]
    banks_mode: Literal["auto", "custom"]
    data_as_of: dict[str, Optional[str]]
    scenarios: Optional[dict] = None
    warnings: list[str] = Field(default_factory=list)
    plan_request: dict


# ----------------------------------------------------------------------------- helpers
def _split_for(req: PlanRequest) -> dict[str, float]:
    """Fractions per bucket key (stock/mf/bank): zero for unchosen classes, summing to 1 over the chosen."""
    chosen = [_BUCKET_OF[c] for c in req.classes]
    if req.manual_split:
        raw = {_BUCKET_OF[c]: v for c, v in req.manual_split.items()}
    else:
        base = _bucket_split(req.risk_thermometer)       # the engine's own risk-based split
        raw = {k: base[k] for k in chosen}
    total = sum(raw.values()) or 1.0
    return {k: (raw.get(k, 0.0) / total if k in chosen else 0.0) for k in _BUCKETS}


def _data_as_of() -> dict[str, Optional[str]]:
    with get_engine().connect() as conn:
        s = conn.execute(select(func.max(prices.c.date))).scalar()
        m = conn.execute(select(func.max(mf_nav.c.date))).scalar()
    return {"stocks": str(s) if s else None, "mf": str(m) if m else None}


def _scenario_returns(label: str, base_mu: float, instrument_type: str, horizon: int) -> tuple[float, float]:
    """Post-tax (bear, bull) annual returns from the forecaster's cached scenario band; falls back to the
    base return when an instrument has no cached scenarios. Always bear <= base <= bull."""
    path = repo_path("data", "forecasts", f"{label}.json")
    bear = bull = base_mu
    try:
        scen = json.loads(path.read_text(encoding="utf-8")).get("scenarios") or {}
        if "bear" in scen:
            bear = post_tax_return(scen["bear"]["cagr_pct"] / 100.0, instrument_type, horizon)
        if "bull" in scen:
            bull = post_tax_return(scen["bull"]["cagr_pct"] / 100.0, instrument_type, horizon)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return min(bear, base_mu), max(bull, base_mu)


def _explanation(req: PlanRequest, split: dict[str, float], buckets: list) -> str:
    names = {"stock": "Stocks", "mf": "Mutual Funds", "bank": "Bank FD"}
    shares = " / ".join(f"{split[k] * 100:.0f}% {names[k]}" for k in _BUCKETS if split[k] > 0)
    head = (f"Based on a risk level of {req.risk_thermometer:.0f}/100 and a {req.horizon_years}-year horizon, "
            f"your capital of Rs.{req.capital:,.0f} was split {shares}. ")
    body = "".join(
        f"{b.label}: Rs.{b.present_value:,.0f} -> Rs.{b.projected_value:,.0f} ({b.projected_return_pct:.1f}%/yr post-tax). "
        for b in buckets if b.present_value > 0
    )
    return head + body


def build_plan(req: PlanRequest, profile_id: Optional[str] = None) -> PlanResult:
    pid = profile_id or req.profile_id or str(uuid.uuid4())
    h = req.horizon_years
    split = _split_for(req)
    custom_choices = (set(req.classes) != set(_ALL_CLASSES) or req.sector_pref or req.mf_category_pref
                      or req.banks != "auto" or req.manual_split)
    profile = UserProfile(
        profile_id=pid, mode="knowledgeable" if custom_choices else "naive",
        capital=req.capital, risk_thermometer=req.risk_thermometer, horizon_years=h,
        sector_pref=req.sector_pref if "stocks" in req.classes else [],
        mf_category_pref=req.mf_category_pref if "mf" in req.classes else [],
    )

    # Stock and mutual fund legs: the engine as-is, funded only for the chosen equity classes.
    equity_weights, equity_ips = [], []
    stock_bp = mf_bp = None
    equity_vol, equity_present = 0.0, 0.0
    if split["stock"] > 0 or split["mf"] > 0:
        res = allocate(profile, bucket_split_override={**split, "bank": 0.0})
        equity_weights = [w for w in res.weights if w.amount > 0.005]
        equity_ips = [p for p in res.instrument_projections if p.present_value > 0.005]
        by_label = {b.label: b for b in res.bucket_projections}
        stock_bp, mf_bp = by_label.get("Stocks"), by_label.get("Mutual Funds")
        equity_present = sum(b.present_value for b in (stock_bp, mf_bp) if b)
        equity_vol = res.expected_volatility_pct
    stock_bp = stock_bp or bucket_projection("Stocks", [], h)
    mf_bp = mf_bp or bucket_projection("Mutual Funds", [], h)

    # FD leg: chosen banks, or the best 5 for this risk band; equal split.
    bank_weights, bank_ips, warnings = [], [], []
    bank_capital = req.capital * split["bank"]
    if bank_capital > 0:
        if req.banks == "auto":
            banks = select_banks(req.risk_thermometer, n_banks=AUTO_BANK_COUNT, record_pick=False)
        else:
            by_id = {b["id"]: b for b in _load_banks()}
            banks = [by_id[i] for i in req.banks]
        per_bank = bank_capital / len(banks)
        for b in banks:
            bank_weights.append(InstrumentWeight(label=b["id"], display_name=b["display_name"], bucket="bank",
                                                 weight_pct=100.0 / len(banks), amount=per_bank))
            bank_ips.append(instrument_projection(
                b["display_name"], per_bank, post_tax_return(b["rate_pct"] / 100.0, "fd", h), h))
        if per_bank > DEPOSIT_INSURANCE_LIMIT:
            warnings.append(
                f"About Rs.{per_bank:,.0f} goes to each bank. Deposit insurance covers up to Rs.5,00,000 per "
                "bank, so consider choosing more banks.")
    bank_bp = bucket_projection("Bank/FD", bank_ips, h)

    buckets = [stock_bp, mf_bp, bank_bp]
    total_present = sum(b.present_value for b in buckets)
    total_projected = sum(b.projected_value for b in buckets)
    expected_return = ((total_projected / total_present) ** (1 / h) - 1) * 100 if total_present > 0 else 0.0
    # FD volatility is treated as 0, as in allocate(): re-weight the equity volatility by the new total.
    expected_vol = equity_vol * equity_present / total_present if total_present > 0 else 0.0

    # Scenario range from the forecaster's bear / bull cases (not a statistical percentile).
    scen = {"bear": 0.0, "base": 0.0, "bull": 0.0}
    base_by_name = {p.label: p.projected_return_pct / 100.0 for p in equity_ips}
    for w in equity_weights:
        base_mu = base_by_name.get(w.display_name, 0.0)
        itype = "stock" if w.bucket == "stock" else "mf_equity"
        bear, bull = _scenario_returns(w.label, base_mu, itype, h)
        for key, mu in (("bear", bear), ("base", base_mu), ("bull", bull)):
            scen[key] += w.amount * (1 + mu) ** h
    fd_projected = bank_bp.projected_value
    scenarios = None
    if equity_weights:
        scenarios = {
            k: {"projected_value": scen[k] + fd_projected,
                "return_pct": (((scen[k] + fd_projected) / total_present) ** (1 / h) - 1) * 100}
            for k in ("bear", "base", "bull")
        }

    as_of = _data_as_of()
    newest = [d for d in as_of.values() if d]
    if newest and (date.today() - date.fromisoformat(min(newest))).days > STALE_AFTER_DAYS:
        warnings.append(f"Prices are from {min(newest)}; the daily data refresh may be overdue.")

    request_dump = req.model_dump()
    request_dump["profile_id"] = pid
    result = PlanResult(
        profile_id=pid, mode=profile.mode, risk_thermometer=req.risk_thermometer, horizon_years=h,
        weights=equity_weights + bank_weights, expected_return_pct=expected_return,
        expected_volatility_pct=expected_vol, explanation_text=_explanation(req, split, buckets),
        bucket_projections=buckets, instrument_projections=equity_ips + bank_ips, banks_selected=bank_weights,
        classes=list(req.classes), split_pct={k: round(split[k] * 100, 2) for k in _BUCKETS},
        banks_mode="auto" if req.banks == "auto" else "custom", data_as_of=as_of,
        scenarios=scenarios, warnings=warnings, plan_request=request_dump,
    )
    _persist_profile_allocation(pid, profile, result)   # one stored row per profile_id, as for /allocate
    return result


def _stored_request(profile_id: str) -> tuple[dict, PlanRequest]:
    stored = _load_stored_profile(profile_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="No saved plan for this profile_id.")
    alloc = stored["allocation_json"]
    saved = alloc.get("plan_request")
    if saved is None:   # allocation made by the older /allocate: rebuild its inputs
        saved = {
            "capital": sum(b["present_value"] for b in alloc["bucket_projections"]),
            "horizon_years": stored["horizon_years"], "risk_thermometer": stored["risk_thermometer"],
        }
    return alloc, PlanRequest(**{**saved, "profile_id": profile_id})


# ----------------------------------------------------------------------------- routes
@router.post("/plan")
def create_plan(req: PlanRequest) -> dict:
    return build_plan(req).model_dump()


@router.get("/plan/{profile_id}")
def get_plan(profile_id: str) -> dict:
    alloc, req = _stored_request(profile_id)
    if "plan_request" in alloc:
        return alloc
    return build_plan(req, profile_id).model_dump()


@router.patch("/plan/{profile_id}")
def update_plan(profile_id: str, patch: PlanPatch) -> dict:
    old_alloc, current = _stored_request(profile_id)
    changes = patch.model_dump(exclude_unset=True)
    merged = {**current.model_dump(), **{k: v for k, v in changes.items() if v is not None or k == "manual_split"}}
    if "classes" in changes and "manual_split" not in changes:
        merged["manual_split"] = None          # new class list: back to the risk-based split
    try:
        new_req = PlanRequest(**merged)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    new = build_plan(new_req, profile_id).model_dump()
    return {"allocation": new, "diff": _build_diff(old_alloc, new)}


@router.post("/plan/{profile_id}/rebalance")
def rebalance_plan(profile_id: str, body: PlanRebalance) -> dict:
    old_alloc, current = _stored_request(profile_id)
    if (body.pct is None) == (body.amount is None):
        raise HTTPException(status_code=422, detail="Give exactly one of pct or amount.")
    if body.from_bucket == body.to_bucket:
        raise HTTPException(status_code=422, detail="from and to must differ.")

    total = current.capital
    split = _split_for(current)
    if split.get(body.from_bucket, 0.0) <= 0:
        raise HTTPException(status_code=422, detail="There is no money in that class to move.")
    requested = total * body.pct / 100.0 if body.pct is not None else float(body.amount)
    moved_frac = min(split[body.from_bucket], requested / total)
    new_split = dict(split)
    new_split[body.from_bucket] -= moved_frac
    new_split[body.to_bucket] += moved_frac

    key_of = {v: k for k, v in _BUCKET_OF.items()}
    classes = [key_of[k] for k in _BUCKETS if new_split[k] > 1e-9]       # a class emptied by the move is dropped
    manual = {key_of[k]: round(new_split[k] * 100, 4) for k in _BUCKETS if new_split[k] > 1e-9}
    drift = 100 - sum(manual.values())
    manual[classes[0]] = round(manual[classes[0]] + drift, 4)              # make it add up to exactly 100
    new_req = current.model_copy(update={"classes": classes, "manual_split": manual})
    new = build_plan(new_req, profile_id).model_dump()
    moved_amount = round(moved_frac * total, 2)
    return {
        "allocation": new, "diff": _build_diff(old_alloc, new), "moved_amount": moved_amount,
        "requested_amount": round(requested, 2), "capped": moved_amount < requested - 0.5,
    }


@router.get("/banks")
def list_banks() -> list[dict]:
    return [
        {"id": b["id"], "display_name": b["display_name"], "tier": b["tier"], "category": b["category"],
         "rate_pct": b["rate_pct"]}
        for b in sorted(_load_banks(), key=lambda x: x["rate_pct"], reverse=True)
    ]


@router.get("/data-status")
def data_status() -> dict:
    as_of = _data_as_of()
    return {**as_of, "checked_at": datetime.now().isoformat(timespec="seconds")}
