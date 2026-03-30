# TODO: Pydantic schemas for the Inventory domain
#
# --- Stock Level Schemas ---
# StockLevelRead
#   - product_id: UUID
#   - product_name: str
#   - quantity_on_hand: int
#   - quantity_reserved: int
#   - quantity_available: int
#   - low_stock_threshold: int
#   - is_low_stock: bool (computed: quantity_available <= low_stock_threshold)
#   - last_replenished_at: datetime | None
#   - updated_at: datetime
#
# StockLevelListResponse
#   - items: list[StockLevelRead]
#   - total: int
#   - page: int
#   - page_size: int
#
# StockAdjustment
#   - product_id: UUID
#   - quantity_change: int (positive to add, negative to remove)
#   - movement_type: str ("manual_add" | "manual_remove" | "damaged" | "correction")
#   - reason: str (required for manual adjustments)
#
# --- Stock Movement Schemas ---
# StockMovementRead
#   - id: UUID
#   - product_id: UUID
#   - movement_type: str
#   - quantity_change: int
#   - quantity_before: int
#   - quantity_after: int
#   - reference_id: UUID | None
#   - reference_type: str | None
#   - reason: str | None
#   - performed_by: UUID
#   - created_at: datetime
#
# --- Alert Schemas ---
# LowStockAlertRead
#   - id: UUID
#   - product_id: UUID
#   - product_name: str
#   - threshold: int
#   - current_quantity: int
#   - deficit: int (computed: threshold - current_quantity)
#   - status: str
#   - triggered_at: datetime
#
# ThresholdUpdate
#   - low_stock_threshold: int (>= 0)
#
# AlertSettings
#   - default_threshold: int
#   - notification_enabled: bool
#   - notification_channels: list[str] (e.g. ["email", "in_app"])
#
# --- Forecast Schemas ---
# DepletionForecast
#   - product_id: UUID
#   - product_name: str
#   - current_stock: int
#   - avg_daily_depletion: float
#   - days_until_stockout: int | None (None if no sales data)
#   - estimated_stockout_date: date | None
#   - confidence: float (0.0 to 1.0)
#
# --- Auto-Depletion Schemas ---
# DepletionRequest
#   - sale_id: UUID
#   - product_id: UUID
#   - quantity: int
#
# DepletionReversalRequest
#   - sale_id: UUID
#   - product_id: UUID
#   - quantity: int
