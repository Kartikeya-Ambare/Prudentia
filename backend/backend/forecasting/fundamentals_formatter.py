""" present/projected value per instrument and per bucket.

`projected_value = present_value * (1 + mu_post_tax) ** horizon_years`, using
each instrument's own post-tax forecasted mu already computed by
forecaster.py -> tax_engine.py — this module only surfaces those numbers at
the instrument and bucket level, it does no forecasting or tax logic itself.
"""
from __future__ import annotations

from shared.schemas.models import ValueProjection


def instrument_projection(
    label: str, present_value: float, mu_post_tax: float, horizon_years: int,
) -> ValueProjection:
    projected_value = present_value * (1 + mu_post_tax) ** horizon_years
    return ValueProjection(
        label=label,
        present_value=present_value,
        projected_value=projected_value,
        projected_return_pct=mu_post_tax * 100,
        horizon_years=horizon_years,
    )


def bucket_projection(
    label: str, instrument_projections: list[ValueProjection], horizon_years: int,
) -> ValueProjection:
    present = sum(p.present_value for p in instrument_projections)
    projected = sum(p.projected_value for p in instrument_projections)
    # Weighted-average annualized return implied by present -> projected,
    # not a simple mean of the instruments' own rates.
    implied_annual_return = (projected / present) ** (1 / horizon_years) - 1 if present > 0 else 0.0
    return ValueProjection(
        label=label,
        present_value=present,
        projected_value=projected,
        projected_return_pct=implied_annual_return * 100,
        horizon_years=horizon_years,
    )
