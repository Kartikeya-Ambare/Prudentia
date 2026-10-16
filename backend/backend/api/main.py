"""FastAPI entrypoint. Run with:
    uvicorn backend.api.main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI

from backend.api.routes import router as core_router
from backend.api.routes_drift import router as drift_router
from backend.api.routes_plan import router as plan_router
from backend.config import get_config
from backend.db import init_db

app = FastAPI(title=get_config().app.name)

init_db()  # idempotent — safe to call at import time

# Fill the in-memory price/NAV memo in the background so the first plan request is not the slow one.
import threading  # noqa: E402

from backend.data.cache_manager import warm_cache  # noqa: E402

threading.Thread(target=warm_cache, name="warm-cache", daemon=True).start()

app.include_router(core_router)
app.include_router(drift_router)
app.include_router(plan_router)     # plans: asset classes, bank choice, partial updates (additive)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
