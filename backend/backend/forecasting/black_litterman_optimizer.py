"""Default OptimizerStrategy implementation. Blends the forecaster's
per-instrument view (mu_post_tax) with a historical-mean equilibrium prior via
PyPortfolioOpt's Black-Litterman model, then runs mean-variance optimization
with a risk_thermometer-driven risk-aversion coefficient.
"""
from __future__ import annotations

import logging

import pandas as pd
from pypfopt import BlackLittermanModel, EfficientFrontier, expected_returns, risk_models

from backend.config import get_config
from backend.forecasting.optimizer_base import OptimizerStrategy
from shared.schemas.models import InstrumentWeight

logger = logging.getLogger(__name__)


class BlackLittermanOptimizer(OptimizerStrategy):
    def optimize(
        self,
        mu_post_tax: dict[str, float],
        price_histories: dict[str, pd.Series],
        risk_thermometer: float,
        constraints: dict,
    ) -> tuple[dict, list[InstrumentWeight]]:
        bucket = constraints.get("bucket", "stock")
        usable = {t: price_histories[t] for t in mu_post_tax if t in price_histories and len(price_histories[t]) >= 30}

        if len(usable) < 2:
            return self._equal_weight_fallback(mu_post_tax, bucket)

        prices_df = pd.DataFrame(usable).ffill().dropna()
        # Some sources (mfapi.in's older NAV history in particular) contain
        # literal 0.0 rows from bad historical data; a zero here would blow
        # up PyPortfolioOpt's pct_change-based return/covariance math, so
        # forward-fill over non-positive prices the same way as real gaps.
        prices_df = prices_df.mask(prices_df <= 0).ffill().dropna()
        if prices_df.shape[0] < 30 or prices_df.shape[1] < 2:
            return self._equal_weight_fallback(mu_post_tax, bucket)
        views = {t: mu_post_tax[t] for t in prices_df.columns}

        try:
            cov = risk_models.CovarianceShrinkage(prices_df).ledoit_wolf()
            pi = expected_returns.mean_historical_return(prices_df)
            # `pi` is a *raw* historical mean, with none of forecaster.py's
            # guardrails applied to it — a single past run-up can put it at
            # 80-90%+ annualized for a name with a short/volatile history.
            # Left unclipped, that single number can dominate the BL
            # posterior for that instrument even at a middling view
            # confidence, pulling the optimizer's weights toward an
            # instrument our own (guarded) forecast does not actually
            # support — silently undoing every guardrail in forecaster.py
            # for exactly the one place they were meant to protect. This is
            # a numerical-plausibility bound on the optimizer's own prior,
            # not a duplicate of the forecaster's guardrail layer.
            prior_cap_pct = get_config().optimizer.get("prior_cagr_cap_pct", 40) / 100.0
            pi = pi.clip(lower=-prior_cap_pct, upper=prior_cap_pct)
            confidence = constraints.get("view_confidence", 0.5)
            bl = BlackLittermanModel(
                cov, pi=pi, absolute_views=views,
                view_confidences=[confidence] * len(views),
            )
            bl_ret = bl.bl_returns()
            bl_cov = bl.bl_cov()

            max_weight = constraints.get("max_weight_per_instrument", 0.35)
            ef = EfficientFrontier(bl_ret, bl_cov, weight_bounds=(0, max_weight))
            ef.max_quadratic_utility(risk_aversion=self._risk_aversion(risk_thermometer))
            cleaned = ef.clean_weights(cutoff=0.01)
            perf = ef.portfolio_performance(verbose=False)
        except Exception as exc:
            logger.warning("Black-Litterman optimization failed (%s), falling back to equal weight", exc)
            return self._equal_weight_fallback(mu_post_tax, bucket)

        weights = [
            InstrumentWeight(label=t, display_name=t, bucket=bucket, weight_pct=w * 100, amount=0.0)
            for t, w in cleaned.items() if w > 0
        ]
        metrics = {"expected_return_pct": perf[0] * 100, "expected_volatility_pct": perf[1] * 100}
        return metrics, weights

    @staticmethod
    def _risk_aversion(risk_thermometer: float) -> float:
        # 0 (most conservative) -> aversion 10 ; 100 (most aggressive) -> aversion 1
        return max(1.0, 10.0 - (risk_thermometer / 100.0) * 9.0)

    @staticmethod
    def _equal_weight_fallback(mu_post_tax: dict[str, float], bucket: str) -> tuple[dict, list[InstrumentWeight]]:
        n = len(mu_post_tax)
        if n == 0:
            return {"expected_return_pct": 0.0, "expected_volatility_pct": 0.0}, []
        w_pct = 100.0 / n
        weights = [
            InstrumentWeight(label=t, display_name=t, bucket=bucket, weight_pct=w_pct, amount=0.0)
            for t in mu_post_tax
        ]
        avg_ret = sum(mu_post_tax.values()) / n * 100
        return {"expected_return_pct": avg_ret, "expected_volatility_pct": 0.0}, weights


OPTIMIZER_REGISTRY = {
    "black_litterman": BlackLittermanOptimizer,
}
