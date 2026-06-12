"""Stock count domain exceptions."""

import uuid


class StockCountNotFoundError(Exception):
    def __init__(self, stock_count_id: uuid.UUID) -> None:
        self.stock_count_id = stock_count_id
        super().__init__(f"Stock count {stock_count_id} not found")


class StockCountFinalizedError(Exception):
    def __init__(self, stock_count_id: uuid.UUID) -> None:
        self.stock_count_id = stock_count_id
        super().__init__(
            f"Stock count {stock_count_id} is already finalized and cannot be modified"
        )
