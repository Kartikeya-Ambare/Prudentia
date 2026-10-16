"""In-memory session store: keyed by session_id, TTL + max turns from config, 1 msg/sec per session."""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


class RateLimited(Exception):
    pass


@dataclass
class Session:
    session_id: str
    params: dict[str, Any] = field(default_factory=dict)       # amount, years, risk, classes
    awaiting: list[str] = field(default_factory=list)          # slots the bot just asked for
    result: Optional[dict] = None                              # current AllocationResult
    profile_id: Optional[str] = None
    history: list[tuple[dict, dict]] = field(default_factory=list)   # (params, result) snapshots, oldest first
    pending: Optional[dict] = None                             # {params, result} waiting for "haan"/"nahi"
    risk_scenario: dict = field(default_factory=dict)          # {"step": 0..2, "points": int}
    last_fund: Optional[str] = None                            # last mutual fund discussed (for follow-ups)
    turns: int = 0
    last_ts: float = 0.0
    created: float = 0.0

    def snapshot(self) -> None:
        if self.result is not None:
            self.history.append((copy.deepcopy(self.params), copy.deepcopy(self.result)))
            del self.history[:-5]


class SessionStore:
    def __init__(self, ttl_minutes: float = 120, max_turns: int = 30, min_interval: float = 1.0,
                 clock: Callable[[], float] = time.monotonic):
        self.ttl, self.max_turns, self.min_interval, self.clock = ttl_minutes * 60, max_turns, min_interval, clock
        self._s: dict[str, Session] = {}

    def get(self, session_id: str) -> Session:
        now = self.clock()
        self._sweep(now)
        s = self._s.get(session_id)
        if s is None:
            s = self._s[session_id] = Session(session_id, created=now, last_ts=-1e9)
        return s

    def touch(self, s: Session) -> None:
        """Rate-limit check + bookkeeping. Raises RateLimited when messages arrive faster than 1/min_interval."""
        now = self.clock()
        if now - s.last_ts < self.min_interval:
            raise RateLimited()
        s.last_ts = now
        s.turns += 1

    def over_limit(self, s: Session) -> bool:
        return s.turns > self.max_turns

    def _sweep(self, now: float) -> None:
        dead = [k for k, v in self._s.items() if now - max(v.last_ts, v.created) > self.ttl]
        for k in dead:
            del self._s[k]

    def reset(self, session_id: str) -> None:
        self._s.pop(session_id, None)
