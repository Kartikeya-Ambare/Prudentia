"""Scheme-name <-> AMFI-code lookup for API routes. Reads the cache
universe_builder.py already wrote — never resolves live inside a request."""
from __future__ import annotations

import json

from backend.config import repo_path

CODE_CACHE_PATH = repo_path("universe", "mf_scheme_codes.json")


def _load_name_to_code() -> dict[str, str]:
    if not CODE_CACHE_PATH.exists():
        return {}
    raw = json.loads(CODE_CACHE_PATH.read_text(encoding="utf-8"))
    return {name: code for name, code in raw.items() if code}


def resolve_code(fund_name: str) -> str | None:
    return _load_name_to_code().get(fund_name)


def code_to_name_map() -> dict[str, str]:
    return {code: name for name, code in _load_name_to_code().items()}
