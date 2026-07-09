"""AI Engine domain Pydantic schemas."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Single source of truth — import from service to avoid divergence
from src.ai_engine.service import HIGH_CONSEQUENCE_ACTIONS, HUMAN_REVIEW_REASON


# ---------------------------------------------------------------------------
# Recommendation schemas
# ---------------------------------------------------------------------------

_UNDER_TRAINED_DISCLAIMER = (
    "Recommendation is based on limited historical data (<30 data points). "
    "Treat with caution and validate against your own business knowledge."
)


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
    # E1 — AI confidence disclosure
    data_points_used: int = 0
    confidence_reliable: bool = False
    under_trained_model: str | None = None
    # E4 — Human review gate
    requires_human_review: bool = False
    human_review_reason: str | None = None
    # E7 — Explainability
    reason_summary: str = ""
    evidence: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _populate_ethical_fields(self) -> "RecommendationRead":
        """Populate ethical disclosure fields from expected_impact metadata."""
        impact = self.expected_impact or {}
        # E1 — confidence disclosure
        if self.data_points_used == 0 and "data_points_used" in impact:
            self.data_points_used = int(impact["data_points_used"])
        self.confidence_reliable = self.data_points_used >= 30
        if not self.confidence_reliable and self.under_trained_model is None:
            self.under_trained_model = _UNDER_TRAINED_DISCLAIMER
        else:
            self.under_trained_model = None  # clear stale disclaimer when model is reliable
        # E4 — human review gate
        action_str = (
            self.action_type.value
            if hasattr(self.action_type, "value")
            else str(self.action_type)
        )
        if action_str in HIGH_CONSEQUENCE_ACTIONS:
            self.requires_human_review = True
            self.human_review_reason = HUMAN_REVIEW_REASON
        # E7 — explainability
        if not self.reason_summary and "reason_summary" in impact:
            self.reason_summary = impact["reason_summary"]
        if not self.evidence and "evidence" in impact:
            self.evidence = impact["evidence"]
        return self


class RecommendationListResponse(BaseModel):
    items: list[RecommendationRead]
    total: int
    by_category: dict[str, int] = Field(default_factory=dict)
    by_priority: dict[str, int] = Field(default_factory=dict)
    ai_available: bool = True
    degraded_reason: str | None = None


class RecommendationAccept(BaseModel):
    notes: str | None = None
    confirmed: bool = False  # E4: required for DELAY_PAYMENT / LIQUIDATE


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
    preferred_rate_percentile: Decimal = Field(ge=0, le=100, default=Decimal("25"))
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
