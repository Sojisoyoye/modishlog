"""Orders domain Pydantic schemas."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Line item schemas
# ---------------------------------------------------------------------------


class OrderLineItemCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(..., gt=0)
    unit_cost: Decimal = Field(..., gt=0)
    notes: str | None = None


class OrderLineItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    unit_cost: Decimal
    line_total: Decimal
    notes: str | None = None


# ---------------------------------------------------------------------------
# Purchase order schemas
# ---------------------------------------------------------------------------


class OrderCreate(BaseModel):
    supplier_name: str = Field(..., min_length=1, max_length=255)
    supplier_contact: str | None = None
    currency: str = "USD"
    fx_rate_at_creation: Decimal | None = None
    expected_delivery_date: date | None = None
    production_days: int | None = None
    shipping_days: int | None = None
    clearing_days: int | None = None
    shipping_cost: Decimal = Field(default=Decimal("0"), ge=0)
    clearing_cost: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = None
    line_items: list[OrderLineItemCreate] = Field(..., min_length=1)


class OrderUpdate(BaseModel):
    supplier_name: str | None = None
    supplier_contact: str | None = None
    expected_delivery_date: date | None = None
    notes: str | None = None
    line_items: list[OrderLineItemCreate] | None = None


class PaymentSummary(BaseModel):
    total_due: Decimal
    total_paid: Decimal
    balance_remaining: Decimal
    payment_count: int
    is_fully_paid: bool


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_number: str
    supplier_name: str
    supplier_contact: str | None = None
    status: str
    total_amount: Decimal
    currency: str
    fx_rate_at_creation: Decimal | None = None
    shipping_cost: Decimal = Decimal("0")
    clearing_cost: Decimal = Decimal("0")
    expected_delivery_date: date | None = None
    actual_delivery_date: date | None = None
    notes: str | None = None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    line_items: list[OrderLineItemRead] = []


class OrderDetailRead(OrderRead):
    payment_summary: PaymentSummary | None = None


class OrderListResponse(BaseModel):
    items: list[OrderRead]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Status workflow schemas
# ---------------------------------------------------------------------------


class StatusTransition(BaseModel):
    new_status: str
    actual_delivery_date: date | None = None
    notes: str | None = None


class StatusHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_status: str | None = None
    to_status: str
    transitioned_by: uuid.UUID
    notes: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Payment schemas
# ---------------------------------------------------------------------------


class PaymentCreate(BaseModel):
    amount: Decimal = Field(..., gt=0)
    currency: str = "USD"
    payment_date: date
    payment_method: str = Field(
        ..., pattern="^(bank_transfer|lc|cash)$"
    )
    reference: str | None = None
    notes: str | None = None


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    amount: Decimal
    currency: str
    payment_date: date
    payment_method: str
    reference: str | None = None
    status: str
    notes: str | None = None
    recorded_by: uuid.UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# Reporting schemas
# ---------------------------------------------------------------------------


class OrdersSummary(BaseModel):
    total_orders: int
    total_value: Decimal
    by_status: dict[str, int]


# ---------------------------------------------------------------------------
# Logistics Efficiency schemas
# ---------------------------------------------------------------------------


class OrderLogisticsRead(BaseModel):
    order_id: uuid.UUID
    order_number: str
    logistics_pct: Decimal
    logistics_ngn: Decimal
    total_cogs_ngn: Decimal


class LogisticsEfficiencyResponse(BaseModel):
    per_order: list[OrderLogisticsRead]
    rolling_90d_avg_pct: Decimal
    amber_threshold_pct: Decimal
    red_threshold_pct: Decimal
    status: str  # "healthy", "amber", "red"
