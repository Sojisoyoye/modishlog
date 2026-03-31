"""AI Engine domain Pydantic schemas."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Recommendation schemas
# ---------------------------------------------------------------------------


class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: str
    title: str
    description: str
    priority: str
    confidence: Decimal
    expected_impact: dict | None = None
    action_type: str
    action_payload: dict | None = None
    reference_id: uuid.UUID | None = None
    reference_type: str | None = None
    status: str
    created_at: datetime
    expires_at: datetime


class RecommendationListResponse(BaseModel):
    items: list[RecommendationRead]
    total: int
    by_category: dict[str, int] = Field(default_factory=dict)
    by_priority: dict[str, int] = Field(default_factory=dict)


class RecommendationAccept(BaseModel):
    notes: str | None = None


class RecommendationDismiss(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ImpactSummary(BaseModel):
    total_pending: int
    projected_revenue_impact: Decimal
    projected_cost_savings: Decimal
    by_category: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# USD Strategy schemas
# ---------------------------------------------------------------------------


class USDScheduleEntry(BaseModel):
    week: int
    purchase_date: date
    usd_amount: Decimal
    forecasted_fx_rate: Decimal
    ngn_amount: Decimal


class USDAccumulationScheduleResponse(BaseModel):
    order_id: uuid.UUID
    total_usd_needed: Decimal
    weeks: int
    weekly_amount: Decimal
    schedule: list[USDScheduleEntry]


class USDStrategyConfigCreate(BaseModel):
    target_usd_balance: Decimal = Field(gt=0)
    risk_tolerance: str = "moderate"
    max_single_purchase_pct: Decimal = Field(ge=0, le=100, default=Decimal("10"))
    preferred_rate_percentile: Decimal = Field(
        ge=0, le=100, default=Decimal("25")
    )
    lookback_days: int = Field(ge=30, le=365, default=90)


class USDStrategyConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    target_usd_balance: Decimal
    current_usd_balance: Decimal
    risk_tolerance: str
    max_single_purchase_pct: Decimal
    preferred_rate_percentile: Decimal
    lookback_days: int
    updated_at: datetime


# ---------------------------------------------------------------------------
# Reorder suggestion schemas
# ---------------------------------------------------------------------------


class ReorderSuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    current_stock: int
    reorder_point: int
    suggested_order_quantity: int
    economic_order_quantity: int
    safety_stock: int
    lead_time_days: int
    avg_daily_demand: Decimal
    estimated_stockout_date: date | None = None
    confidence: Decimal
    reasoning: str
    status: str
    created_at: datetime


class ReorderSuggestionListResponse(BaseModel):
    items: list[ReorderSuggestionRead]
    total: int
    critical_count: int
