"""Frozen API contract. Every backend module imports these shapes from here rather than redefining them;
the frontend's `src/api/types.ts` mirrors this file."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, conint, confloat


class UserProfile(BaseModel):
    profile_id: Optional[str] = None
    mode: Literal["naive", "knowledgeable"]
    capital: confloat(gt=0)
    risk_thermometer: confloat(ge=0, le=100)
    horizon_years: conint(ge=1, le=40)
    sector_pref: list[str] = Field(default_factory=list)       # knowledgeable mode only,
    mf_category_pref: list[Literal["Large Cap", "Mid Cap", "Small Cap"]] = Field(default_factory=list)


class InstrumentWeight(BaseModel):
    label: str                                   # ticker, scheme code, or bank id
    display_name: str
    bucket: Literal["stock", "mf", "bank"]
    weight_pct: confloat(ge=0, le=100)
    amount: confloat(ge=0)


class ValueProjection(BaseModel):
    label: str
    present_value: float
    projected_value: float
    projected_return_pct: float
    horizon_years: conint(ge=1, le=40)


class AllocationExplanation(BaseModel):
    profile_id: str
    mode: Literal["naive", "knowledgeable"]
    risk_thermometer: float
    horizon_years: int
    weights: list[InstrumentWeight]
    expected_return_pct: float
    expected_volatility_pct: float
    explanation_text: str                         # Jinja2-rendered, never LLM-generated numbers
    bucket_projections: list[ValueProjection]      # length 3: Stocks/MF/Bank
    instrument_projections: list[ValueProjection]  # one per held instrument
    banks_selected: list[InstrumentWeight]
