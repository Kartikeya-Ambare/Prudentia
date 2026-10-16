"""Post-tax return conversion — Indian capital-gains regime.

This is a *return-annualization* approximation, not a full tax-return
calculator: it answers "what annualized return should the optimizer see
after tax?", not "what tax do I owe this year?". The equity LTCG exemption
(config.tax.equity_ltcg_exemption) is a per-financial-year, portfolio-wide
allowance, not something that cleanly divides across one forecasted
instrument's mu — it is deliberately NOT netted into per-instrument mu here,
to avoid a false precision this tool can't back up. It belongs at the
aggregate-portfolio level if/when the UI reports an actual realized-gain
estimate, not inside a single instrument's forward-looking return.
"""
from __future__ import annotations

from typing import Literal

from backend.config import get_config

InstrumentType = Literal["stock", "mf_equity", "mf_debt", "fd"]


def post_tax_return(mu_pretax: float, instrument_type: InstrumentType, horizon_years: float) -> float:
    """mu_pretax: annualized pre-tax expected return (decimal, e.g. 0.12).
    horizon_years: intended holding period, used only to pick STCG vs LTCG
    for equity instruments — debt MFs and FDs are slab-taxed regardless.
    """
    cfg = get_config().tax
    if instrument_type in ("stock", "mf_equity"):
        is_long_term = horizon_years * 365 >= cfg.equity_ltcg_threshold_days
        rate = cfg.equity_ltcg_rate if is_long_term else cfg.equity_stcg_rate
    elif instrument_type in ("mf_debt", "fd"):
        rate = cfg.default_slab_rate
    else:
        raise ValueError(f"unknown instrument_type {instrument_type!r}")

    if mu_pretax <= 0:
        # Losses/zero return aren't taxed — don't apply a "tax benefit" that
        # would make a losing position look better post-tax than pre-tax.
        return mu_pretax
    return mu_pretax * (1 - rate)
