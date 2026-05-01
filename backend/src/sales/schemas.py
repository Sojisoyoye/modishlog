"""Sales domain Pydantic schemas."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Sale schemas
# ---------------------------------------------------------------------------


class SaleCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(..., gt=0)
    unit_price: Decimal = Field(..., gt=0)
    sale_date: date
    channel: str = Field(..., pattern="^(online|retail|wholesale)$")
    notes: str | None = None


class SaleUpdate(BaseModel):
    quantity: int | None = Field(None, gt=0)
    unit_price: Decimal | None = Field(None, gt=0)
    sale_date: date | None = None
    channel: str | None = Field(None, pattern="^(online|retail|wholesale)$")
    notes: str | None = None


class DailyEntryItem(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(..., gt=0)
    sale_date: date


class DailyEntryRequest(BaseModel):
    entries: list[DailyEntryItem] = Field(..., min_length=1)


class SaleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    unit_price: Decimal
    total_amount: Decimal
    currency: str
    sale_date: date
    channel: str
    status: str
    notes: str | None = None
    recorded_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class SaleListResponse(BaseModel):
    items: list[SaleRead]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Bulk upload schemas
# ---------------------------------------------------------------------------


class BulkUploadResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    message: str


class BulkUploadStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    status: str
    total_rows: int
    processed_rows: int
    successful_rows: int
    failed_rows: int
    error_details: dict | None = None
    created_at: datetime
    completed_at: datetime | None = None


# ---------------------------------------------------------------------------
# Audit schemas
# ---------------------------------------------------------------------------


class AuditEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sale_id: uuid.UUID
    action: str
    field_changes: dict | None = None
    performed_by: uuid.UUID
    reason: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Reporting schemas
# ---------------------------------------------------------------------------


class SalesSummary(BaseModel):
    period: str
    total_revenue: Decimal
    total_units_sold: int
    transaction_count: int


class SalesHistoryEntry(BaseModel):
    date: date
    revenue: Decimal
    units_sold: int
    transaction_count: int


# ---------------------------------------------------------------------------
# Quick Quote schemas
# ---------------------------------------------------------------------------


class QuickQuoteRequest(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(..., gt=0)


class QuickQuoteResponse(BaseModel):
    product_id: uuid.UUID
    quantity: int
    fifo_landed_cost_per_unit: Decimal
    floor_margin_pct: Decimal
    min_sell_price_per_unit: Decimal
    total_min_price: Decimal
