# TODO: Async service functions for the Inventory domain
#
# --- Stock Levels ---
# async def get_stock_level(db, product_id: UUID) -> StockLevel
#   - Fetch current stock for a product
#   - Raise ProductStockNotFoundError if no stock record exists
#
# async def list_stock_levels(db, filters: dict, page: int, page_size: int) -> tuple[list[StockLevel], int]
#   - Filter by: low stock only, product category, search by name
#   - Join with Product for product_name
#
# async def adjust_stock(db, adjustment: StockAdjustment, user_id: UUID) -> StockMovement
#   - Validate product exists
#   - Apply quantity change to StockLevel
#   - Create StockMovement record
#   - Check if new level triggers or resolves a LowStockAlert
#
# async def get_stock_history(db, product_id: UUID, page: int, page_size: int) -> tuple[list[StockMovement], int]
#   - Return chronological stock movements for a product
#
# --- Low Stock Alerts ---
# async def get_active_alerts(db) -> list[LowStockAlert]
#   - Return all alerts with status "active", ordered by deficit (most critical first)
#
# async def update_threshold(db, product_id: UUID, threshold: int) -> StockLevel
#   - Update low_stock_threshold on StockLevel
#   - Re-evaluate if an alert should be triggered or resolved
#
# async def check_and_trigger_alerts(db, product_id: UUID) -> LowStockAlert | None
#   - Compare current stock to threshold
#   - Create alert if below threshold and no active alert exists
#   - Resolve alert if stock is above threshold
#   - Send notification if configured
#
# --- Depletion Forecast ---
# async def forecast_depletion(db, product_id: UUID) -> DepletionForecast
#   - Calculate average daily depletion from last 30/60/90 days of sales data
#   - Estimate days until stockout
#   - Compute confidence based on sales data variance
#
# async def bulk_forecast(db) -> list[DepletionForecast]
#   - Run forecast for all active products
#   - Sort by days_until_stockout ascending (most urgent first)
#
# --- Auto-Depletion from Sales ---
# async def deplete_from_sale(db, request: DepletionRequest, user_id: UUID) -> StockMovement
#   - Reduce stock by sale quantity
#   - Create StockMovement with type "sale_depletion" and reference to sale_id
#   - Check and trigger low stock alert if needed
#   - Raise InsufficientStockError if quantity_available < requested quantity
#
# async def reverse_depletion(db, request: DepletionReversalRequest, user_id: UUID) -> StockMovement
#   - Restore stock from a voided sale
#   - Create StockMovement with type "sale_reversal"
#   - Resolve low stock alert if stock now above threshold
#
# async def get_depletion_log(db, page: int, page_size: int) -> tuple[list[StockMovement], int]
#   - Filter stock movements where movement_type in ("sale_depletion", "sale_reversal")
