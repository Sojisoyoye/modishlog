"""FX domain Pydantic schemas."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# FX Rate schemas
# ---------------------------------------------------------------------------


class FXRateIngest(BaseModel):
    pair: str = Field(..., min_length=6, max_length=6)
    rate: Decimal = Field(..., gt=0)
    source: str = Field(
        ..., pattern="^(cbn_official|parallel_market|manual|api_provider)$"
    )
    timestamp: datetime | None = None


class FXRateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pair: str
    rate: Decimal
    source: str
    timestamp: datetime
    created_at: datetime


class FXRateHistory(BaseModel):
    pair: str
    rates: list[FXRateRead]
    period_high: Decimal
    period_low: Decimal
    period_avg: Decimal
    pct_change: float


# ---------------------------------------------------------------------------
# Exposure schemas
# ---------------------------------------------------------------------------


class ExposureSummary(BaseModel):
    pair: str
    total_exposure: Decimal
    locked_amount: Decimal
    locked_pct: float
    floating_amount: Decimal
    floating_pct: float
    weighted_locked_rate: Decimal
    current_market_rate: Decimal
    unrealized_pnl: Decimal


class ExposureDetailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pair: str
    total_exposure_amount: Decimal
    locked_amount: Decimal
    locked_rate: Decimal
    floating_amount: Decimal
    reference_id: uuid.UUID | None = None
    reference_type: str | None = None


class ExposureLockRequest(BaseModel):
    pair: str = Field(..., min_length=6, max_length=6)
    amount_to_lock: Decimal = Field(..., gt=0)
    lock_rate: Decimal = Field(..., gt=0)
    reference_id: uuid.UUID | None = None
    reference_type: str | None = None


class ExposureConfigUpdate(BaseModel):
    locked_pct: Decimal = Field(..., ge=0, le=100)
    floating_pct: Decimal = Field(..., ge=0, le=100)


class ExposureConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    locked_pct: Decimal
    floating_pct: Decimal
    updated_by: uuid.UUID
    updated_at: datetime


# ---------------------------------------------------------------------------
# Alert schemas
# ---------------------------------------------------------------------------


class FXAlertCreate(BaseModel):
    pair: str = Field(..., min_length=6, max_length=6)
    direction: str = Field(..., pattern="^(above|below)$")
    threshold_rate: Decimal = Field(..., gt=0)


class FXAlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pair: str
    direction: str
    threshold_rate: Decimal
    is_enabled: bool
    is_triggered: bool
    triggered_at: datetime | None = None
    triggered_rate: Decimal | None = None
    created_by: uuid.UUID
    created_at: datetime


class FXAlertUpdate(BaseModel):
    threshold_rate: Decimal | None = None
    is_enabled: bool | None = None


# ---------------------------------------------------------------------------
# Monte Carlo simulation schemas
# ---------------------------------------------------------------------------


class SimulationRequest(BaseModel):
    pair: str = Field(..., min_length=6, max_length=6)
    horizon_days: int = Field(..., ge=1, le=365)
    num_simulations: int = Field(default=10000, ge=1000, le=100000)
    confidence_level: Decimal = Field(default=Decimal("95.00"), ge=1, le=99)


class SimulationResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pair: str
    horizon_days: int
    num_simulations: int
    confidence_level: Decimal
    current_rate: Decimal
    mean_projected_rate: Decimal
    p5_rate: Decimal
    p50_rate: Decimal
    p95_rate: Decimal
    var_amount: Decimal
    created_at: datetime


class SimulationDistribution(BaseModel):
    sim_id: uuid.UUID
    buckets: list[dict]


# ---------------------------------------------------------------------------
# Volatility schema
# ---------------------------------------------------------------------------


class VolatilityRead(BaseModel):
    pair: str
    days: int
    volatility: Decimal
    data_points: int


# ---------------------------------------------------------------------------
# Forecast schemas
# ---------------------------------------------------------------------------


class ForecastRequest(BaseModel):
    pair: str = Field(..., min_length=6, max_length=6)
    horizon_days: int = Field(default=180, ge=1, le=365)
    num_simulations: int = Field(default=10000, ge=1000, le=100000)


class ForecastRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pair: str
    forecast_date: datetime
    base_rate: Decimal
    best_case_rate: Decimal
    worst_case_rate: Decimal
    prophet_lower: Decimal
    prophet_upper: Decimal
    model_version: str
    mae: Decimal | None = None
    mape: Decimal | None = None
    generated_at: datetime


class ForecastRangeResponse(BaseModel):
    pair: str
    forecasts: list[ForecastRead]
    model_version: str


class ForecastAccuracy(BaseModel):
    pair: str
    total_evaluated: int
    mean_mae: Decimal
    mean_mape: Decimal
