"""Inventory domain exceptions."""


class ProductStockNotFoundError(Exception):
    """Raised when no stock record exists for a product."""

    def __init__(self, product_id):
        self.product_id = product_id
        super().__init__(f"No inventory record for product: {product_id}")


class InsufficientStockError(Exception):
    """Raised when available stock is too low for a depletion."""

    def __init__(self, product_id, requested: int, available: int):
        self.product_id = product_id
        self.requested_quantity = requested
        self.available_quantity = available
        super().__init__(
            f"Insufficient stock for {product_id}: "
            f"requested={requested}, available={available}"
        )


class InvalidStockAdjustmentError(Exception):
    """Raised when adjustment would result in negative stock."""

    def __init__(self, product_id, adjustment: int, current: int):
        self.product_id = product_id
        self.adjustment_quantity = adjustment
        self.current_quantity = current
        super().__init__(
            f"Adjustment would result in negative stock for {product_id}: "
            f"current={current}, adjustment={adjustment}"
        )
