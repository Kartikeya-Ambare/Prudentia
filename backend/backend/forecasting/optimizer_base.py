"""OptimizerStrategy interface. Frozen alongside /shared/schemas —
orchestrator.py never imports a concrete optimizer class directly, only
`OPTIMIZER_REGISTRY[config.optimizer.strategy]`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from shared.schemas.models import InstrumentWeight


class OptimizerStrategy(ABC):
    @abstractmethod
    def optimize(
        self,
        mu_post_tax: dict[str, float],
        price_histories: dict[str, pd.Series],
        risk_thermometer: float,
        constraints: dict,
    ) -> tuple[dict, list[InstrumentWeight]]:
        """Returns (metrics, weights).

        metrics: {"expected_return_pct": float, "expected_volatility_pct": float}
        weights: list[InstrumentWeight] with bucket="stock"/"mf", amount left at 0
                 (orchestrator.py scales amount from capital * weight_pct once the
                 stock/MF split between buckets is decided — this call only prices
                 one bucket's candidate pool at a time).
        """
        ...
