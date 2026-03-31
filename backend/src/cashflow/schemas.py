"""Cashflow domain Pydantic schemas."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Loan schemas
# ---------------------------------------------------------------------------


class LoanCreate(BaseModel):
    lender_name: str
    principal_amount: Decimal = Field(gt=0)
    interest_rate: Decimal = Field(ge=0, le=100)
    term_months: int = Field(ge=1)
    start_date: date
    payment_frequency: str = "monthly"
    monthly_payment: Decimal = Field(gt=0)
    currency: str = "NGN"
    notes: str | None = None


class LoanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lender_name: str
    principal_amount: Decimal
    outstanding_balance: Decimal
    interest_rate: Decimal
    term_months: int
    start_date: date
    end_date: date
    payment_frequency: str
    monthly_payment: Decimal
    currency: str
    status: str
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Operating Cost schemas
# ---------------------------------------------------------------------------


class OperatingCostCreate(BaseModel):
    cost_name: str
    cost_amount: Decimal = Field(gt=0)
    frequency: str  # daily, weekly, monthly, quarterly, annually
    category: str = "other"


class OperatingCostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cost_name: str
    cost_amount: Decimal
    frequency: str
    monthly_equivalent: Decimal
    category: str
    is_active: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Projection schemas
# ---------------------------------------------------------------------------


class MonthlyBucket(BaseModel):
    month: str
    projected_revenue: Decimal
    projected_loan_payment: Decimal
    projected_operating_costs: Decimal
    projected_fx_obligations: Decimal
    net_cashflow: Decimal
    cumulative_cashflow: Decimal
    dscr: Decimal
    cash_runway_months: Decimal
    risk_rating: str


class ProjectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    projection_date: date
    horizon_months: int
    monthly_buckets: list[dict] | None = None
    total_inflows: Decimal
    total_outflows: Decimal
    net_cashflow: Decimal
    assumptions: dict | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# DSCR schemas
# ---------------------------------------------------------------------------


class DSCRResponse(BaseModel):
    dscr: Decimal
    net_operating_income: Decimal
    total_debt_service: Decimal
    color: str


# ---------------------------------------------------------------------------
# Runway schemas
# ---------------------------------------------------------------------------


class RunwayResponse(BaseModel):
    runway_months: Decimal
    avg_monthly_burn: Decimal


# ---------------------------------------------------------------------------
# Scenario schemas
# ---------------------------------------------------------------------------


class ScenarioRequest(BaseModel):
    scenario_type: str = "FX_SHOCK_10"


class ScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    revenue_shock_pct: Decimal
    fx_shock_pct: Decimal
    cost_shock_pct: Decimal
    stressed_dscr: Decimal
    stressed_runway_months: int
    created_at: datetime


class ScenarioComparisonResponse(BaseModel):
    base: dict
    stressed: dict


# ---------------------------------------------------------------------------
# Alert schemas
# ---------------------------------------------------------------------------


class AlertResponse(BaseModel):
    month: str
    type: str
    severity: str
    message: str
