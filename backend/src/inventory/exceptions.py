# TODO: Domain-specific exceptions for the Inventory domain
#
# ProductStockNotFoundError(Exception)
#   - Raised when no stock record exists for a given product.
#   - Attributes: product_id
#
# InsufficientStockError(Exception)
#   - Raised when a depletion is requested but available stock is too low.
#   - Attributes: product_id, requested_quantity, available_quantity
#
# InvalidStockAdjustmentError(Exception)
#   - Raised when a stock adjustment would result in negative stock.
#   - Attributes: product_id, adjustment_quantity, current_quantity
#
# AlertAlreadyExistsError(Exception)
#   - Raised when attempting to create a low-stock alert that already exists for a product.
#   - Attributes: product_id, existing_alert_id
#
# ForecastDataInsufficient(Exception)
#   - Raised when there is not enough historical sales data to compute a reliable forecast.
#   - Attributes: product_id, available_days, required_days
