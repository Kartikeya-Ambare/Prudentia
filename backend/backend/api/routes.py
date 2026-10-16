"""Mutual-fund lookups: the fund list, and each fund's sector allocation and history.
Plans and drift checks are in routes_plan.py and routes_drift.py."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.data.cache_manager import (
    get_latest_sector_allocation, get_sector_history,
    list_mf_schemes_with_sector_data,
)
from backend.data.mf_lookup import code_to_name_map, resolve_code

router = APIRouter()


@router.get("/mutual-funds")
def list_mutual_funds() -> list[dict]:
    name_map = code_to_name_map()
    rows = list_mf_schemes_with_sector_data()
    return [
        {
            "scheme_code": r["scheme_code"],
            "fund_name": name_map.get(r["scheme_code"], r["scheme_code"]),
            "last_updated": r["last_updated"],
        }
        for r in rows
    ]


@router.get("/mutual-funds/{fund_name}/sector-allocation")
def get_sector_allocation(fund_name: str) -> dict:
    code = resolve_code(fund_name)
    if not code:
        raise HTTPException(status_code=404, detail=f"Unknown fund {fund_name!r}")
    row = get_latest_sector_allocation(code)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No sector-allocation data yet for {fund_name!r}")
    return row


@router.get("/mutual-funds/{fund_name}/sector-history")
def get_sector_history_route(fund_name: str) -> list[dict]:
    code = resolve_code(fund_name)
    if not code:
        raise HTTPException(status_code=404, detail=f"Unknown fund {fund_name!r}")
    return get_sector_history(code)
