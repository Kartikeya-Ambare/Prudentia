import pytest

from backend.forecasting.tax_engine import post_tax_return


def test_equity_ltcg_beats_stcg():
    long_term = post_tax_return(0.15, "stock", horizon_years=3)
    short_term = post_tax_return(0.15, "stock", horizon_years=0.5)
    assert long_term > short_term  # LTCG rate (12.5%) < STCG rate (20%)


def test_negative_returns_are_not_taxed():
    assert post_tax_return(-0.10, "stock", horizon_years=3) == -0.10
    assert post_tax_return(0.0, "fd", horizon_years=1) == 0.0


def test_fd_and_debt_mf_use_slab_rate_regardless_of_horizon():
    fd_short = post_tax_return(0.07, "fd", horizon_years=0.5)
    fd_long = post_tax_return(0.07, "fd", horizon_years=5)
    assert fd_short == fd_long


def test_unknown_instrument_type_raises():
    with pytest.raises(ValueError):
        post_tax_return(0.1, "crypto", horizon_years=1)
