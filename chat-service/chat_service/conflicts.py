"""Detects a message that asks for contradicting edits ('remove FD and add FD', 'risk 30% and risk 70%').
Such a message is never applied: the user is asked to send one change at a time."""
from __future__ import annotations

import re
from typing import Optional

from chat_service.guardrails.chat_guardrails import classes_in, normalise, years_in
from chat_service.parse import _ADD, _REMOVE, parse_years

_CLAUSES = re.compile(r"\s*(?:,|;|\band\b|\baur\b|\bthen\b|\bphir\b|&)\s*", re.I)
_RISK_PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)\s*(?:risk|jokhim)|(?:risk|jokhim)\s*(?:to|=|:|ko)?\s*(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)", re.I)
_CORRECTION = re.compile(r"\b(nahi|nahin|nhi|no|not|actually|sorry|i\s+mean|matlab|oops|galat|correction|instead|balki)\b", re.I)


def find_conflict(text: str) -> Optional[str]:
    t = normalise(text)
    if _CORRECTION.search(t):
        return None                                           # 'x, no sorry y': the user is correcting, last value wins
    removed: set[str] = set()
    added: set[str] = set()
    for clause in _CLAUSES.split(t):
        cls = classes_in(clause)
        if not cls:
            continue
        if _REMOVE.search(clause):
            removed |= cls
        elif _ADD.search(clause):
            added |= cls
    if removed & added:
        return "asset classes"
    vals = {float(a or b) for a, b in _RISK_PCT.findall(t)}
    if len(vals) > 1:
        return "risk"
    if len(years_in(t)) > 1 and parse_years(t) is None:        # '3 years and 10 years' (but 'from 5 years to 10 years' is a change)
        return "years"
    return None
