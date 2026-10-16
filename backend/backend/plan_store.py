"""Stored-plan helpers shared by the plan, rebalance and drift endpoints: load a saved allocation, split it by
bucket, diff two allocations, and check a saved plan for drift."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from backend.db import get_engine, profile_allocations
from backend.orchestrator import allocate
from shared.schemas.models import UserProfile

_BUCKET_LABEL_TO_KEY = {"Stocks": "stock", "Mutual Funds": "mf", "Bank/FD": "bank"}


def _load_stored_profile(profile_id: str | None) -> dict | None:
    if not profile_id:
        return None
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            select(profile_allocations).where(profile_allocations.c.profile_id == profile_id)
        ).mappings().first()
    return dict(row) if row else None


def _bucket_split_from_allocation(allocation_json: dict) -> dict[str, float]:
    present = {
        _BUCKET_LABEL_TO_KEY[bp["label"]]: bp["present_value"]
        for bp in allocation_json["bucket_projections"] if bp["label"] in _BUCKET_LABEL_TO_KEY
    }
    total = sum(present.values())
    if total <= 0:
        return {"stock": 0.34, "mf": 0.33, "bank": 0.33}
    return {k: v / total for k, v in present.items()}


def _total_capital(allocation_json: dict) -> float:
    return sum(bp["present_value"] for bp in allocation_json["bucket_projections"])


def _build_diff(old: dict, new: dict) -> list[dict]:
    old_by_label = {bp["label"]: bp["present_value"] for bp in old["bucket_projections"]}
    new_by_label = {bp["label"]: bp["present_value"] for bp in new["bucket_projections"]}
    labels = sorted(set(old_by_label) | set(new_by_label))
    return [
        {
            "bucket": label,
            "before": old_by_label.get(label, 0.0),
            "after": new_by_label.get(label, 0.0),
            "delta": new_by_label.get(label, 0.0) - old_by_label.get(label, 0.0),
        }
        for label in labels
    ]


def check_drift(profile_id: str) -> dict:
    """Recomputes the allocation for a stored profile's original inputs and
    compares it against what's stored — used by GET /rebalance-check/{profile_id}."""
    stored = _load_stored_profile(profile_id)
    if stored is None:
        return {"found": False, "drifted": False, "message": "No saved allocation for this profile_id."}

    old_alloc = stored["allocation_json"]
    profile = UserProfile(
        profile_id=profile_id, mode=stored["mode"], capital=_total_capital(old_alloc),
        risk_thermometer=stored["risk_thermometer"], horizon_years=stored["horizon_years"],
    )
    fresh_split = _bucket_split_from_allocation(old_alloc)  # keep the user's current bucket split fixed;
    # only instrument-level weights within each bucket should drift from price movement, not the
    # bucket split itself (that's a deliberate user/risk choice, not something drift-checking should undo)
    fresh_alloc = allocate(profile, bucket_split_override=fresh_split)

    diff = _build_diff(old_alloc, fresh_alloc.model_dump())
    materially_drifted = any(abs(d["delta"]) > 0.01 * _total_capital(old_alloc) for d in diff)
    return {
        "found": True, "drifted": materially_drifted, "diff": diff,
        "checked_at": datetime.now().isoformat(), "stored_updated_at": str(stored["updated_at"]),
    }
