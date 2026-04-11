"""Inventory domain Pydantic schemas."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Stock level schemas
# ---------------------------------------------------------------------------


class InventoryLevelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
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
    unit_cost_usd: float
    fx_rate_at_arrival: float
    logistics_allocation_per_unit: float
    landed_cost_per_unit: float
    received_at: date
    created_at: datetime


class LiquidationCandidate(BaseModel):
    batch_id: uuid.UUID
    product_id: uuid.UUID
    quantity_remaining: int
    landed_cost_per_unit: float
    total_batch_value: float
    discount_pct_needed: float
