"""Per-instrument return forecaster.

The model is a small Transformer encoder; its hyperparameters live in config.yaml under `forecaster:`. Device
selection is `torch.device("cuda" if torch.cuda.is_available() else "cpu")`, with a silent CPU fallback: CUDA is
never a hard requirement.

Forecasts are cache-first: a trained model + its (mu, sigma) forecast are persisted under
`data/forecasts/<ticker>.json` (+ `.pt` weights) and only retrained once the
cache is older than `forecaster.cache_max_age_hours` (default: once daily,
same cadence as download.py).
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn

from backend.config import get_config, repo_path
from backend.forecasting import forecast_guardrails as guardrails

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252
FORECAST_CACHE_DIR = repo_path("data", "forecasts")


class ReturnForecaster(nn.Module):
    """Small Transformer-encoder regressor: a window of past daily log
    returns -> next-day expected log return."""

    def __init__(self, d_model: int = 32, nhead: int = 4, num_layers: int = 2, window: int = 30):
        super().__init__()
        self.window = window
        self.input_proj = nn.Linear(1, d_model)
        self.pos_embedding = nn.Parameter(torch.zeros(1, window, d_model))
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=d_model * 4,
            batch_first=True, dropout=0.1,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.head = nn.Linear(d_model, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, window, 1)
        h = self.input_proj(x) + self.pos_embedding
        h = self.encoder(h)
        last = h[:, -1, :]
        return self.head(last).squeeze(-1)


def _device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _build_sequences(log_returns: np.ndarray, window: int) -> tuple[torch.Tensor, torch.Tensor]:
    xs, ys = [], []
    for i in range(len(log_returns) - window):
        xs.append(log_returns[i:i + window])
        ys.append(log_returns[i + window])
    x = torch.tensor(np.array(xs), dtype=torch.float32).unsqueeze(-1)
    y = torch.tensor(np.array(ys), dtype=torch.float32)
    return x, y


def _cache_path(ticker: str) -> Path:
    safe = ticker.replace("/", "_").replace("\\", "_")
    return FORECAST_CACHE_DIR / f"{safe}.json"


def _load_cache(ticker: str, max_age_hours: float, guardrail_version: int) -> dict | None:
    path = _cache_path(ticker)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        computed_at = datetime.fromisoformat(payload["computed_at"])
    except Exception:
        return None
    if datetime.now() - computed_at > timedelta(hours=max_age_hours):
        return None
    # Defensive: a cache entry written by an earlier, buggier version of this
    # function (e.g. before the zero-price filtering fix) could have NaN/Inf
    # baked in from `json.dumps`' non-standard NaN token — that would
    # otherwise silently poison every downstream calculation until the cache
    # file's age naturally expired. Reject and force a recompute instead.
    if not (math.isfinite(payload.get("mu", float("nan"))) and math.isfinite(payload.get("sigma", float("nan")))):
        return None
    # A cache entry computed before the guardrail layer existed (or under a
    # since-changed guardrail config/version) has no `guarded_mu` baked in —
    # trusting it verbatim would silently feed an unguarded `mu` to the
    # optimizer. Force a recompute instead.
    if payload.get("guardrail_version") != guardrail_version:
        return None
    return payload


def _save_cache(ticker: str, payload: dict) -> None:
    FORECAST_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(ticker).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _apply_guardrails(
    base_result: dict, *, raw_price_series: pd.Series, clean_prices: pd.Series, log_returns: np.ndarray,
    is_fallback_method: bool, guardrail_cfg, horizon_years: float,
) -> dict:
    """Runs `forecast_guardrails.run_guardrails` over a freshly-computed
    (unguarded) forecast and folds the guarded result back into the dict
    forecaster.py caches/returns. `base_result["mu"]` becomes the *guarded*
    value (what reaches the optimizer); `base_result["raw_mu"]` preserves the
    original Transformer-derived value for transparency/debugging.
    """
    if not bool(guardrail_cfg.get("enabled", True)):
        return {**base_result, "raw_mu": base_result["mu"], "guardrail_status": "DISABLED"}

    result = guardrails.run_guardrails(
        raw_mu=base_result["mu"], sigma_annual=base_result["sigma"], raw_price_series=raw_price_series,
        clean_prices=clean_prices, log_returns=log_returns, horizon_years=horizon_years,
        is_fallback_method=is_fallback_method, config=guardrail_cfg,
    )
    return {
        **base_result,
        "mu": result.guarded_mu,
        "raw_mu": result.raw_mu,
        "sigma": result.sigma_annual,
        "current_price": result.current_price,
        "raw_terminal_price": result.raw_terminal_price,
        "guarded_terminal_price": result.guarded_terminal_price,
        "raw_cagr_pct": result.raw_cagr_pct,
        "guarded_cagr_pct": result.guarded_cagr_pct,
        "historical_cagr_pct": result.historical_cagr_pct,
        "historical_cagr_years": result.historical_cagr_years,
        "historical_max_drawdown_pct": result.historical_max_drawdown_pct,
        "confidence_score": result.confidence_score,
        "confidence_status": result.confidence_status,
        "guardrail_status": result.guardrail_status,
        "data_quality_status": result.data_quality_status,
        "soft_cap_applied": result.soft_cap_applied,
        "terminal_cap_applied": result.terminal_cap_applied,
        "flags": result.flags,
        "warnings": result.warnings,
        "trajectory": result.trajectory,
        "scenarios": result.scenarios,
        "horizon_years_used": horizon_years,
    }


def forecast_ticker(ticker: str, price_series: pd.Series, force_refresh: bool = False) -> dict:
    """price_series: a Series of close/adj_close/NAV prices indexed by date,
    ascending. Returns {"mu": annualized expected return (decimal, GUARDED —
    see forecast_guardrails.py), "raw_mu": the pre-guardrail Transformer
    value, "sigma": annualized volatility (decimal), "n_obs": int, plus the
    guardrail diagnostics documented in forecast_guardrails.py}.
    """
    cfg = get_config().forecaster
    max_age = cfg.get("cache_max_age_hours", 24)
    guardrail_cfg = cfg.get("guardrails", {})
    guardrail_version = guardrail_cfg.get("version", 1)
    horizon_years = cfg.get("horizon_years_default", 5)

    if not force_refresh:
        cached = _load_cache(ticker, max_age, guardrail_version)
        if cached:
            return cached

    prices = price_series.dropna().astype(float)
    # Some sources (mfapi.in's older NAV history in particular) contain
    # literal 0.0 rows from bad historical data, not just NaN/None — a
    # zero survives dropna() and np.log(0.0) is -inf, which silently poisons
    # every downstream mean/std/diff computation. Drop non-positive prices
    # outright; they can't be real traded prices.
    prices = prices[prices > 0]
    log_returns = np.diff(np.log(prices.values))
    sigma_daily = float(np.std(log_returns)) if len(log_returns) > 1 else 0.0
    sigma_annual = sigma_daily * math.sqrt(TRADING_DAYS_PER_YEAR)

    window = min(30, max(5, len(log_returns) // 4))
    if len(log_returns) < window + 10:
        # not enough history to train a sequence model — fall back to the
        # historical mean, still annualized the same way
        mu_annual = float(np.mean(log_returns) * TRADING_DAYS_PER_YEAR) if len(log_returns) else 0.0
        result = {"mu": mu_annual, "sigma": sigma_annual, "n_obs": len(log_returns), "method": "historical_mean"}
        result = _apply_guardrails(
            result, raw_price_series=price_series, clean_prices=prices, log_returns=log_returns,
            is_fallback_method=True, guardrail_cfg=guardrail_cfg, horizon_years=horizon_years,
        )
        _save_cache(ticker, {**result, "guardrail_version": guardrail_version, "computed_at": datetime.now().isoformat()})
        return result

    # Normalize to unit scale before training — raw log returns are tiny
    # (~1e-2), which makes a freshly-initialized Transformer's single-step
    # prediction noise-dominated; that noise then explodes once annualized
    # (x252). Training/predicting in units of daily sigma keeps the model
    # well-conditioned, and predictions are rescaled back afterward.
    norm_returns = log_returns / (sigma_daily + 1e-8)

    device = _device()
    model = ReturnForecaster(
        d_model=cfg.get("d_model", 32), nhead=cfg.get("nhead", 4),
        num_layers=cfg.get("num_layers", 2), window=window,
    ).to(device)

    x, y = _build_sequences(norm_returns, window)
    x, y = x.to(device), y.to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=cfg.get("learning_rate", 0.001))
    loss_fn = nn.MSELoss()
    model.train()
    for _ in range(cfg.get("epochs", 30)):
        optimizer.zero_grad()
        pred = model(x)
        loss = loss_fn(pred, y)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

    # Average the model's predicted next-step (normalized) return over the
    # last K overlapping windows rather than trusting a single last-window
    # point prediction — substantially reduces variance before annualizing.
    model.eval()
    k = min(20, len(norm_returns) - window)
    with torch.no_grad():
        eval_x, _ = _build_sequences(norm_returns[-(window + k):], window)
        preds_norm = model(eval_x.to(device)).cpu().numpy()
    mean_pred_norm = float(np.mean(preds_norm))
    mean_pred_daily_log_return = mean_pred_norm * sigma_daily

    # Annualize by simple scaling (not compounding) — consistent with sigma's
    # own sqrt(t) annualization convention and safe for the small per-day
    # magnitudes a next-day-return model produces.
    mu_annual = float(np.clip(mean_pred_daily_log_return * TRADING_DAYS_PER_YEAR, -0.75, 1.5))
    result = {"mu": mu_annual, "sigma": sigma_annual, "n_obs": len(log_returns), "method": "transformer",
              "final_train_loss": float(loss.item())}
    result = _apply_guardrails(
        result, raw_price_series=price_series, clean_prices=prices, log_returns=log_returns,
        is_fallback_method=False, guardrail_cfg=guardrail_cfg, horizon_years=horizon_years,
    )
    _save_cache(ticker, {**result, "guardrail_version": guardrail_version, "computed_at": datetime.now().isoformat()})
    return result
