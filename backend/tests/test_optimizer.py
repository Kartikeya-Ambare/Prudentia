import numpy as np
import pandas as pd
import pytest

from backend.forecasting.black_litterman_optimizer import BlackLittermanOptimizer


def _synthetic_prices(n=300, drift=0.0004, vol=0.015, seed=1) -> pd.Series:
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(drift, vol, n)
    prices = 100 * np.exp(np.cumsum(log_returns))
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    return pd.Series(prices, index=dates)


@pytest.fixture
def two_instrument_setup():
    price_histories = {
        "GOOD.NS": _synthetic_prices(seed=1),
        "BAD.NS": _synthetic_prices(seed=2),
    }
    mu = {"GOOD.NS": 0.20, "BAD.NS": -0.05}
    return mu, price_histories


def test_weights_sum_to_roughly_100(two_instrument_setup):
    mu, price_histories = two_instrument_setup
    opt = BlackLittermanOptimizer()
    metrics, weights = opt.optimize(mu, price_histories, risk_thermometer=50,
                                     constraints={"bucket": "stock", "max_weight_per_instrument": 0.9})
    total = sum(w.weight_pct for w in weights)
    assert 95 <= total <= 100.5


def test_higher_return_instrument_gets_more_weight(two_instrument_setup):
    mu, price_histories = two_instrument_setup
    opt = BlackLittermanOptimizer()
    _, weights = opt.optimize(mu, price_histories, risk_thermometer=50,
                               constraints={"bucket": "stock", "max_weight_per_instrument": 0.9})
    by_label = {w.label: w.weight_pct for w in weights}
    assert by_label["GOOD.NS"] > by_label["BAD.NS"]


def test_equal_weight_fallback_for_insufficient_history():
    opt = BlackLittermanOptimizer()
    mu = {"A": 0.1, "B": 0.1, "C": 0.1}
    metrics, weights = opt.optimize(mu, {}, risk_thermometer=50, constraints={"bucket": "stock"})
    assert len(weights) == 3
    assert all(w.weight_pct == pytest.approx(100 / 3) for w in weights)
