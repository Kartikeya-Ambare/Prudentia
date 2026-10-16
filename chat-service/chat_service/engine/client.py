"""EngineClient: the ONLY way the chat service reaches allocation data.

All results are plain dicts so the same shapes flow from FakeEngine and HttpEngine:

  AllocationResult = {
      profile_id, amount, years, risk_score, classes: [stocks|mf|fd],
      buckets: {stock|mf|bank: {weight_pct, amount}},
      instruments: [{label, display_name, bucket, weight_pct, amount}],
      expected_return_pct, p5_return_pct?, p95_return_pct?,       # annualised %, optional (old /allocate only)
      projected: {p5?, expected?, p95?},                          # rupees at the horizon, optional
      split_pct: {stock|mf|bank: float},                          # plan API: exact split
      banks: "auto" | [bank_id], banks_mode: "auto"|"custom",     # plan API: how the FD banks were chosen
      scenarios: {bear|base|bull: {projected_value, return_pct}}, # plan API, optional (None without equity)
      data_as_of: str | {stocks, mf},                             # plan API sends the dict
      warnings: [str], requires_confirmation: bool, explanation_text
  }
"""
from __future__ import annotations

import re
from typing import Any, Optional, Protocol

AllocationResult = dict[str, Any]


class EngineError(Exception):
    """The engine answered but refused / failed."""


class EngineUnavailable(EngineError):
    """The engine could not be reached at all (connection refused, timeout, DNS)."""


class EngineRejected(EngineError):
    """The engine understood the request but refused it (HTTP 4xx other than 404). `detail` is its message."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


class EngineClient(Protocol):
    def allocate(self, request: dict) -> AllocationResult: ...
    def update_plan(self, profile_id: str, patch: dict) -> dict: ...      # -> {allocation, diff}
    def list_banks(self) -> list[dict]: ...                               # [{id, display_name, rate_pct, ...}]
    def get_allocation(self, profile_id: str) -> Optional[dict]: ...
    def rebalance(self, profile_id: str, from_bucket: str, to_bucket: str,
                  pct: Optional[float] = None, amount: Optional[float] = None) -> dict: ...
    def check_drift(self, profile_id: str) -> dict: ...
    def get_sector_allocation(self, fund_name: str) -> Optional[dict]: ...
    def get_sector_history(self, fund_name: str) -> Optional[list]: ...
    def known_fund_names(self) -> list[str]: ...


_FILLER = {"fund", "funds", "mutual", "mf", "scheme", "plan", "direct", "growth", "the", "ka", "ki", "ke", "me", "mein"}


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def resolve_fund_name(query: str, names: list[str]) -> Optional[str]:
    """'SBI small cap' -> 'SBI Small Cap Fund'. Every meaningful query token must occur in the name."""
    q = _tokens(query) - _FILLER
    if not q:
        return None
    hits = [n for n in names if q <= _tokens(n)]
    if not hits:
        return None
    return min(hits, key=lambda n: len(_tokens(n)))
