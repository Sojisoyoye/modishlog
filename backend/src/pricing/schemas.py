"""Pricing domain Pydantic schemas."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Demand Elasticity schemas
# ---------------------------------------------------------------------------


class ElasticityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    elasticity_coefficient: Decimal
    r_squared: Decimal
    data_points_used: int
    calculation_date: date
    price_range_min: Decimal
    price_range_max: Decimal
    demand_curve_data: dict | None = None
    created_at: datetime


class ElasticityConfigUpdate(BaseModel):
    elasticity_coefficient: Decimal = Field(..., ge=-10, le=0)


# ---------------------------------------------------------------------------
# Portfolio Margin schemas
# ---------------------------------------------------------------------------


class ProductMarginDetail(BaseModel):
    product_id: uuid.UUID
    product_name: str
    unit_cost: Decimal
    selling_price: Decimal
    margin_pct: float
    revenue_30d: Decimal
    cogs_30d: Decimal
    quantity_30d: int


class PortfolioMarginResponse(BaseModel):
    blended_margin: Decimal
    target_margin: Decimal
    margin_gap: Decimal
    total_revenue: Decimal
    total_cogs: Decimal
    products: list[ProductMarginDetail]


class MarginTargetCreate(BaseModel):
    product_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    target_margin_pct: Decimal = Field(..., ge=0, le=100)
    min_margin_pct: Decimal = Field(..., ge=0, le=100)
    priority: int = Field(default=1, ge=1)


class MarginTargetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    target_margin_pct: Decimal
    min_margin_pct: Decimal
    priority: int
    set_by: uuid.UUID


# ---------------------------------------------------------------------------
# Pricing Recommendation schemas
# ---------------------------------------------------------------------------


class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    current_price: Decimal
    recommended_price: Decimal
    expected_demand_change_pct: Decimal
    expected_revenue_change_pct: Decimal
    expected_margin_change_pct: Decimal
    confidence: Decimal
    reasoning: str
    status: str
    applied_at: datetime | None = None
    applied_by: uuid.UUID | None = None
    created_at: datetime


class RecommendationApplyRequest(BaseModel):
    recommendation_ids: list[uuid.UUID]


class GenerateRecommendationsRequest(BaseModel):
    target_margin: Decimal = Field(default=Decimal("35.00"), ge=1, le=99)


# ---------------------------------------------------------------------------
# Demand Forecast schemas
# ---------------------------------------------------------------------------


class DemandForecastDay(BaseModel):
    date: date
    demand: float
    demand_lower: float
    demand_upper: float


class DemandForecastResponse(BaseModel):
    product_id: uuid.UUID
    horizon_days: int
    forecasts: list[DemandForecastDay]
    total_projected_demand: float


# ---------------------------------------------------------------------------
# Cross-Subsidization schemas
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Product Mix Target schemas
# ---------------------------------------------------------------------------


class MixTargetCreate(BaseModel):
    category_id: uuid.UUID
    target_pct: Decimal = Field(..., ge=0, le=100)


class MixTargetBulkCreate(BaseModel):
    targets: list[MixTargetCreate]


class MixTargetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID
    target_pct: Decimal
    created_at: datetime
    updated_at: datetime


class MixCategoryStatus(BaseModel):
    category_id: uuid.UUID
    category_name: str
    actual_pct: Decimal
    target_pct: Decimal
    variance_pct: Decimal


class MixStatusResponse(BaseModel):
    categories: list[MixCategoryStatus]


class CrossSubsidyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_date: date
    portfolio_total_margin: Decimal
    high_margin_products: dict | None = None
    low_margin_products: dict | None = None
    recommendations: dict | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Price-FX Sensitivity Playground schemas
# ---------------------------------------------------------------------------


class SensitivityCalcRequest(BaseModel):
    product_id: uuid.UUID | None = None
    selling_price_override: Decimal = Field(..., gt=0)
    fx_rate_override: Decimal = Field(..., gt=0)
    quantity: int = Field(..., ge=1)
    unit_cost_usd: Decimal | None = Field(default=None, gt=0)


class SensitivityCalcResponse(BaseModel):
    unit_cost_usd: Decimal
    fx_rate: Decimal
    landed_cost_ngn: Decimal
    selling_price: Decimal
    margin_pct: Decimal
    quantity: int
    total_revenue: Decimal
    total_cost: Decimal
    gross_profit: Decimal


# ---------------------------------------------------------------------------
# Selling price suggestion schemas
# ---------------------------------------------------------------------------


class SellingPriceSuggestionRequest(BaseModel):
    product_id: uuid.UUID | None = None
    unit_cost_override: Decimal | None = Field(default=None, gt=0)
    currency: str = Field(default="NGN", max_length=3)
    fx_rate_override: Decimal | None = Field(default=None, gt=0)
    min_margin_pct: Decimal = Field(default=Decimal("35.00"), ge=1, lt=100)

    @model_validator(mode="after")
    def require_cost_source(self) -> "SellingPriceSuggestionRequest":
        if self.product_id is None and self.unit_cost_override is None:
            raise ValueError("Either product_id or unit_cost_override must be provided")
        return self


class SellingPriceSuggestionResponse(BaseModel):
    unit_cost: Decimal
    currency: str
    fx_rate: Decimal
    unit_cost_ngn: Decimal
    min_margin_pct: Decimal
    min_selling_price: Decimal
    fx_rate_stale: bool = False
    fx_rate_source: str = "live"


class ScenarioCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    product_id: uuid.UUID | None = None
    selling_price: Decimal = Field(..., gt=0)
    fx_rate: Decimal = Field(..., gt=0)
    quantity: int = Field(..., ge=1)
    results: dict | None = None


class ScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    product_id: uuid.UUID | None = None
    selling_price: Decimal
    fx_rate: Decimal
    quantity: int
    results: dict | None = None
    created_by: uuid.UUID
    created_at: datetime


class SuggestRequest(BaseModel):
    target_margin_pct: Optional[Decimal] = Field(
        default=None, gt=Decimal("0"), lt=Decimal("1")
    )
    variant_id: Optional[uuid.UUID] = None


class OrderLineSuggestionItem(BaseModel):
    line_item_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    unit_cost_ngn: Decimal
    current_price_ngn: Decimal | None = None
    target_margin_pct: Decimal
    suggested_price_ngn: Decimal | None = None


class OrderPriceSuggestionsResponse(BaseModel):
    order_id: uuid.UUID
    fx_rate_used: Decimal
    items: list[OrderLineSuggestionItem]


class PriceSuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    unit_cost_ngn: Decimal
    fx_rate_used: Decimal
    target_margin_pct: Decimal
    suggested_price_ngn: Decimal
    current_catalog_price_ngn: Decimal | None = None
    suggested_at: datetime
    notes: str | None = None
