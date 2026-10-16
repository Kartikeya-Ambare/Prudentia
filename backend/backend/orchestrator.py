"""The /allocate handler's orchestration. Wires selection ->
forecasting -> tax -> optimization -> projections -> bank selection into one
AllocationExplanation. Never imports a concrete optimizer class directly —
only `OPTIMIZER_REGISTRY[config.optimizer.strategy]`.

The stock/MF/bank capital split comes from `_bucket_split()` below: risk 0 -> mostly FD with a small equity sleeve,
risk 100 -> mostly equity. It is kept in one function so it is the one place to tune.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from jinja2 import Template
from sqlalchemy import select

from backend.config import get_config
from backend.data.cache_manager import get_mf_nav, get_prices
from backend.data.mf_lookup import code_to_name_map
from backend.db import get_engine, profile_allocations
from backend.forecasting.black_litterman_optimizer import OPTIMIZER_REGISTRY
from backend.forecasting.forecaster import forecast_ticker
from backend.forecasting.fundamentals_formatter import bucket_projection, instrument_projection
from backend.forecasting.optimizer_base import OptimizerStrategy
from backend.forecasting.tax_engine import post_tax_return
from backend.selection.bank_selector import select_banks
from backend.selection.universe_selector import select_mf_candidates, select_stock_candidates
from shared.schemas.models import AllocationExplanation, InstrumentWeight, UserProfile, ValueProjection

logger = logging.getLogger(__name__)

EXPLANATION_TEMPLATE = Template(
    "Based on a risk thermometer of {{ risk }}/100 and a {{ horizon }}-year horizon, "
    "your capital of Rs.{{ '{:,.0f}'.format(capital) }} was split "
    "{{ '%.0f'|format(split.stock*100) }}% Stocks / {{ '%.0f'|format(split.mf*100) }}% Mutual Funds / "
    "{{ '%.0f'|format(split.bank*100) }}% Bank-FD. "
    "{% for bp in bucket_projections %}{{ bp.label }}: Rs.{{ '{:,.0f}'.format(bp.present_value) }} -> "
    "Rs.{{ '{:,.0f}'.format(bp.projected_value) }} ({{ '%.1f'|format(bp.projected_return_pct) }}%/yr post-tax). "
    "{% endfor %}"
)


def _bucket_split(risk_thermometer: float) -> dict[str, float]:
    aggressive_frac = risk_thermometer / 100.0
    stock_pct = 0.20 + 0.45 * aggressive_frac    # 20% (risk=0) -> 65% (risk=100)
    mf_pct = 0.30 + 0.15 * aggressive_frac        # 30% -> 45%
    bank_pct = max(1.0 - stock_pct - mf_pct, 0.05)
    total = stock_pct + mf_pct + bank_pct
    return {"stock": stock_pct / total, "mf": mf_pct / total, "bank": bank_pct / total}


def _get_optimizer() -> OptimizerStrategy:
    strategy = get_config().optimizer.strategy
    return OPTIMIZER_REGISTRY[strategy]()


def _optimize_bucket(
    optimizer: OptimizerStrategy, candidates: list[str], price_lookup, instrument_type: str,
    bucket: str, capital: float, risk_thermometer: float, horizon_years: int, max_weight: float,
    display_name_lookup: dict[str, str] | None = None,
) -> tuple[list[InstrumentWeight], list[ValueProjection], float]:
    mu, prices = {}, {}
    for label in candidates:
        series = price_lookup(label)
        if series is None or series.empty:
            continue
        prices[label] = series
        raw = forecast_ticker(label, series)
        mu[label] = post_tax_return(raw["mu"], instrument_type, horizon_years)

    if not mu:
        return [], [], 0.0

    # A fixed max_weight cap is only feasible when the pool has at least
    # ceil(1/max_weight) instruments (weights must sum to 1) — with a small
    # candidate pool (e.g. early in a demo before the full universe is
    # downloaded), relax the cap just enough to stay solvable instead of
    # silently degrading to the equal-weight fallback every time.
    effective_max_weight = max(max_weight, 1.0 / len(mu))

    metrics, weights = optimizer.optimize(mu, prices, risk_thermometer,
                                           {"bucket": bucket, "max_weight_per_instrument": effective_max_weight})
    projections = []
    for w in weights:
        w.amount = capital * w.weight_pct / 100
        w.display_name = (display_name_lookup or {}).get(w.label, w.label)
        projections.append(instrument_projection(w.display_name, w.amount, mu[w.label], horizon_years))
    return weights, projections, float(metrics.get("expected_volatility_pct", 0.0))


def _persist_profile_allocation(profile_id: str, profile: UserProfile, result: AllocationExplanation) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        exists = conn.execute(
            select(profile_allocations.c.profile_id).where(profile_allocations.c.profile_id == profile_id)
        ).first()
        payload = dict(
            profile_id=profile_id, mode=profile.mode, risk_thermometer=profile.risk_thermometer,
            horizon_years=profile.horizon_years, allocation_json=result.model_dump(),
            updated_at=datetime.now(),
        )
        if exists:
            conn.execute(
                profile_allocations.update().where(profile_allocations.c.profile_id == profile_id).values(**payload)
            )
        else:
            conn.execute(profile_allocations.insert().values(**payload))


def allocate(profile: UserProfile, bucket_split_override: dict[str, float] | None = None) -> AllocationExplanation:
    """bucket_split_override requests a specific Stocks/MF/Bank split instead of the
    risk-derived default, so "move 10% from stocks to FD" recomputes against an explicitly
    shifted split rather than the profile's original risk-driven one."""
    profile_id = profile.profile_id or str(uuid.uuid4())
    split = bucket_split_override or _bucket_split(profile.risk_thermometer)
    optimizer = _get_optimizer()

    all_weights: list[InstrumentWeight] = []
    instrument_projections: list[ValueProjection] = []
    bucket_projections: list[ValueProjection] = []

    stock_candidates = select_stock_candidates(profile.risk_thermometer, profile.sector_pref or None)
    stock_weights, stock_ips, stock_vol = _optimize_bucket(
        optimizer, stock_candidates, lambda t: get_prices(t)["adj_close"] if not get_prices(t).empty else None,
        "stock", "stock", profile.capital * split["stock"], profile.risk_thermometer, profile.horizon_years, 0.35,
    )
    all_weights.extend(stock_weights)
    instrument_projections.extend(stock_ips)
    bucket_projections.append(bucket_projection("Stocks", stock_ips, profile.horizon_years))

    mf_candidates = select_mf_candidates(profile.risk_thermometer, profile.mf_category_pref or None)
    mf_weights, mf_ips, mf_vol = _optimize_bucket(
        optimizer, mf_candidates, lambda c: get_mf_nav(c)["nav"] if not get_mf_nav(c).empty else None,
        "mf_equity", "mf", profile.capital * split["mf"], profile.risk_thermometer, profile.horizon_years, 0.40,
        display_name_lookup=code_to_name_map(),
    )
    all_weights.extend(mf_weights)
    instrument_projections.extend(mf_ips)
    bucket_projections.append(bucket_projection("Mutual Funds", mf_ips, profile.horizon_years))

    bank_capital = profile.capital * split["bank"]
    banks_selected: list[InstrumentWeight] = []
    bank_ips: list[ValueProjection] = []
    if bank_capital > 0:
        banks = select_banks(profile.risk_thermometer, n_banks=2)
        if banks:
            per_bank = bank_capital / len(banks)
            for b in banks:
                fd_mu = post_tax_return(b["rate_pct"] / 100.0, "fd", profile.horizon_years)
                iw = InstrumentWeight(
                    label=b["id"], display_name=b["display_name"], bucket="bank",
                    weight_pct=100.0 / len(banks), amount=per_bank,
                )
                banks_selected.append(iw)
                all_weights.append(iw)
                bank_ips.append(instrument_projection(b["display_name"], per_bank, fd_mu, profile.horizon_years))
    instrument_projections.extend(bank_ips)
    bucket_projections.append(bucket_projection("Bank/FD", bank_ips, profile.horizon_years))

    total_present = sum(bp.present_value for bp in bucket_projections)
    total_projected = sum(bp.projected_value for bp in bucket_projections)
    expected_return_pct = (
        ((total_projected / total_present) ** (1 / profile.horizon_years) - 1) * 100 if total_present > 0 else 0.0
    )
    # Capital-weighted average of each bucket's own optimizer-reported volatility
    # (FD leg treated as ~0 vol) — ignores cross-bucket correlation, a known
    # simplification appropriate for a prototype-scale demo, not a risk-desk figure.
    bucket_vols = {"Stocks": stock_vol, "Mutual Funds": mf_vol, "Bank/FD": 0.0}
    expected_volatility_pct = (
        sum(bp.present_value * bucket_vols.get(bp.label, 0.0) for bp in bucket_projections) / total_present
        if total_present > 0 else 0.0
    )

    explanation_text = EXPLANATION_TEMPLATE.render(
        risk=profile.risk_thermometer, horizon=profile.horizon_years, capital=profile.capital,
        split=split, bucket_projections=bucket_projections,
    )

    result = AllocationExplanation(
        profile_id=profile_id, mode=profile.mode, risk_thermometer=profile.risk_thermometer,
        horizon_years=profile.horizon_years, weights=all_weights,
        expected_return_pct=expected_return_pct, expected_volatility_pct=expected_volatility_pct,
        explanation_text=explanation_text, bucket_projections=bucket_projections,
        instrument_projections=instrument_projections, banks_selected=banks_selected,
    )
    _persist_profile_allocation(profile_id, profile, result)
    return result
