"""Pydantic models: the request/response contract and the validated intent."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, confloat

IntentName = Literal[
    "provide_inputs", "modify_inputs", "rebalance", "explain_allocation", "explain_mf_sector",
    "rebalance_check", "ask_result", "ask_app", "compare_funds", "sector_history", "clarify", "unsupported",
]
Bucket = Literal["stock", "mf", "bank"]


class ChatIntent(BaseModel):
    """Same field set as the backend's shared/schemas ChatIntent, plus the Saathi intake intents."""
    intent: IntentName
    profile_id: Optional[str] = None
    move_from_bucket: Optional[Bucket] = None
    move_to_bucket: Optional[Bucket] = None
    move_pct: Optional[confloat(ge=0, le=100)] = None       # "move 10%"
    move_amount: Optional[confloat(ge=0)] = None            # "move 5000": absolute rupees
    target_fund_or_ticker: Optional[str] = None
    clarification_question: Optional[str] = None
    raw_message: str = ""


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str
    profile_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    intent: str
    params: dict[str, Any] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    result: Optional[dict[str, Any]] = None
    blocked: Optional[bool] = None
    category: Optional[str] = None
    session_id: str
