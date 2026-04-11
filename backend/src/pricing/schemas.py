"""Pricing domain Pydantic schemas."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


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
