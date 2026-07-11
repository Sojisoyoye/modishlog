"""Inventory domain Pydantic schemas."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Stock level schemas
# ---------------------------------------------------------------------------


class InventoryLevelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    # NULL for a product's aggregate row; set for a variant-level row (see
    # data_import/recompute.py) — without this, list_inventory_levels()
    # returning more than one row for the same product_id would be
    # indistinguishable duplicates to an API consumer.
    variant_id: uuid.UUID | None = None
    quantity_on_hand: int
    quantity_reserved: int
    low_stock_threshold: int
    last_replenished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class StockAdjustmentRequest(BaseModel):
    quantity_change: int
    movement_type: str = Field(
        ..., pattern="^(manual_add|manual_remove|damaged|order_received)$"
    )
    reason: str = Field(..., min_length=1, max_length=500)


# ---------------------------------------------------------------------------
# Stock movement schemas
# ---------------------------------------------------------------------------


class StockMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    movement_type: str
    quantity_change: int
    quantity_before: int
    quantity_after: int
    reference_id: uuid.UUID | None = None
    reference_type: str | None = None
    reason: str | None = None
    performed_by: uuid.UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# Depletion forecast schemas
# ---------------------------------------------------------------------------


class DepletionForecastRead(BaseModel):
    product_id: uuid.UUID
    current_stock: int
    avg_daily_depletion: float
    days_until_stockout: int | None = None
    estimated_stockout_date: date | None = None


# ---------------------------------------------------------------------------
# Inventory Batch schemas
# ---------------------------------------------------------------------------


class InventoryBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    order_id: uuid.UUID
    quantity_received: int
    quantity_remaining: int
    unit_cost_usd: Decimal
    fx_rate_at_arrival: Decimal
    logistics_allocation_per_unit: Decimal
    landed_cost_per_unit: Decimal
    received_at: date
    created_at: datetime


class ThresholdUpdateRequest(BaseModel):
    low_stock_threshold: int = Field(..., ge=0)


class LiquidationCandidate(BaseModel):
    batch_id: uuid.UUID
    product_id: uuid.UUID
    quantity_remaining: int
    landed_cost_per_unit: Decimal
    total_batch_value: Decimal
    discount_pct_needed: Decimal


class InventoryListResponse(BaseModel):
    items: list[InventoryLevelRead]
    total: int
    page: int
    page_size: int
