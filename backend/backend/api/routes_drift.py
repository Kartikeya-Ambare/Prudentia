"""GET /rebalance-check/{profile_id}: has a saved plan drifted from what the engine would compute today?"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend import plan_store

router = APIRouter()


@router.get("/rebalance-check/{profile_id}")
def rebalance_check(profile_id: str) -> dict:
    result = plan_store.check_drift(profile_id)
    if not result["found"]:
        raise HTTPException(status_code=404, detail=result["message"])
    return result
