"""Resolves MF scheme *names* (universe/mf_universe.yaml seeds, human-readable)
to real AMFI scheme codes (the runtime key everything else uses)

- resolve_scheme_code(name): looks up mfapi.in's search endpoint, caches the
  result in universe/mf_scheme_codes.json so repeated runs don't re-query.
- expand_category_from_amfi(): best-effort fill toward
  max_schemes_per_category using AMFI's public scheme master, matched by
  scheme-name keyword heuristics (AMFI's list has no clean machine-readable
  category tag in the free NAVAll.txt feed, so this is heuristic, not exact —
  it only ever *adds* schemes, never replaces the verified seed list, and any
  scheme it can't confidently categorize is skipped rather than guessed).
"""
from __future__ import annotations

import json
import logging
import re

import requests
import yaml

from backend.config import repo_path

logger = logging.getLogger(__name__)

MFAPI_SEARCH_URL = "https://api.mfapi.in/mf/search"
AMFI_NAVALL_URL = "https://www.amfiindia.com/spages/NAVAll.txt"
CODE_CACHE_PATH = repo_path("universe", "mf_scheme_codes.json")

CATEGORY_KEYWORDS = {
    "large_cap": [r"\blarge\s*cap\b", r"\bbluechip\b", r"\bfrontline\s*equity\b"],
    "mid_cap": [r"\bmid\s*cap\b", r"\bmidcap\b"],
    "small_cap": [r"\bsmall\s*cap\b", r"\bsmallcap\b"],
}


def _load_cache() -> dict:
    if CODE_CACHE_PATH.exists():
        return json.loads(CODE_CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict) -> None:
    CODE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CODE_CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def resolve_scheme_code(name: str, cache: dict | None = None, timeout: int = 10) -> str | None:
    """Best-effort exact/substring match against mfapi.in's search results."""
    own_cache = cache is None
    if cache is None:
        cache = _load_cache()
    if name in cache:
        return cache[name]

    try:
        resp = requests.get(MFAPI_SEARCH_URL, params={"q": name}, timeout=timeout)
        resp.raise_for_status()
        results = resp.json()
    except Exception as exc:  # network/parse failure — log and skip, never crash the run
        logger.warning("resolve_scheme_code(%r) failed: %s", name, exc)
        return None

    code = None
    for r in results:
        if r.get("schemeName", "").strip().lower() == name.strip().lower():
            code = str(r["schemeCode"])
            break
    if code is None and results:
        code = str(results[0]["schemeCode"])  # closest fuzzy match mfapi returned

    cache[name] = code
    if own_cache:
        _save_cache(cache)
    return code


def resolve_all_seeds(mf_universe_path=None) -> dict:
    """Resolves every seed_schemes entry in mf_universe.yaml. Returns
    {scheme_name: scheme_code_or_None} and persists the cache."""
    path = mf_universe_path or repo_path("universe", "mf_universe.yaml")
    with open(path, "r", encoding="utf-8") as f:
        mf_universe = yaml.safe_load(f)

    cache = _load_cache()
    for category in mf_universe["categories"].values():
        for name in category["seed_schemes"]:
            if name not in cache:
                resolve_scheme_code(name, cache=cache)
    _save_cache(cache)
    return cache


def expand_category_from_amfi(category_key: str, existing_names: set[str],
                               target_count: int, timeout: int = 20) -> dict:
    """Returns {scheme_name: scheme_code} of additional schemes matched by
    keyword heuristics against AMFI's NAVAll.txt, up to target_count new
    entries. Never raises — returns {} on any fetch/parse failure."""
    patterns = CATEGORY_KEYWORDS.get(category_key, [])
    if not patterns:
        return {}
    try:
        resp = requests.get(AMFI_NAVALL_URL, timeout=timeout)
        resp.raise_for_status()
        lines = resp.text.splitlines()
    except Exception as exc:
        logger.warning("expand_category_from_amfi(%s) fetch failed: %s", category_key, exc)
        return {}

    found: dict[str, str] = {}
    combined = re.compile("|".join(patterns), re.IGNORECASE)
    for line in lines:
        parts = line.split(";")
        if len(parts) < 4:
            continue
        scheme_code, _isin1, _isin2, scheme_name = parts[0], parts[1], parts[2], parts[3]
        if not scheme_code.strip().isdigit():
            continue
        if scheme_name.strip() in existing_names:
            continue
        if combined.search(scheme_name) and "direct" not in scheme_name.lower():
            # Prefer Growth plans; skip IDCW/Dividend variants to avoid NAV-series distortion.
            if "idcw" in scheme_name.lower() or "dividend" in scheme_name.lower():
                continue
            found[scheme_name.strip()] = scheme_code.strip()
            if len(found) >= target_count:
                break
    return found
