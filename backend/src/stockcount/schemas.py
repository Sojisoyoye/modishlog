"""Stock count Pydantic schemas."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field


class StockCountCreate(BaseModel):
    count_date: date
    count_type: Literal["PRODUCT", "LOT"]
    notes: Optional[str] = None


class StockCountItemUpdate(BaseModel):
    counted_quantity: Decimal = Field(ge=Decimal("0"))


class StockCountItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    stock_count_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str = ""
    order_line_item_id: Optional[uuid.UUID] = None
    system_quantity_at_count: Optional[Decimal] = None
    counted_quantity: Optional[Decimal] = None
    notes: Optional[str] = None

    @computed_field
    @property
    def variance(self) -> Optional[Decimal]:
        if self.system_quantity_at_count is None or self.counted_quantity is None:
            return None
        return self.counted_quantity - self.system_quantity_at_count


class StockCountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    count_date: date
    count_type: str
    status: str
    notes: Optional[str] = None
    created_by: uuid.UUID
    finalized_at: Optional[datetime] = None
    created_at: datetime
    items: list[StockCountItemRead] = []


class StockCountListRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    count_date: date
    count_type: str
    status: str
    notes: Optional[str] = None
    created_at: datetime
    finalized_at: Optional[datetime] = None
    item_count: int = 0
