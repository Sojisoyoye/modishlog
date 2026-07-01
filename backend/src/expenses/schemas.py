import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ExpenseCategoryCreate(BaseModel):
    name: str = Field(..., max_length=150)
    description: str | None = None


class ExpenseCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime


class ExpenseCreate(BaseModel):
    category_id: uuid.UUID | None = None
    ref_no: str | None = None
    amount_ngn: Decimal = Field(..., ge=0)
    fx_rate: Decimal | None = None
    amount_usd: Decimal = Field(..., ge=0)
    currency: str = "USD"
    expense_date: date
    payment_method: str | None = None
    note: str | None = None
    location_id: uuid.UUID | None = None


class ExpenseUpdate(BaseModel):
    category_id: uuid.UUID | None = None
    ref_no: str | None = None
    amount_ngn: Decimal | None = Field(None, ge=0)
    fx_rate: Decimal | None = None
    amount_usd: Decimal | None = Field(None, ge=0)
    currency: str | None = None
    expense_date: date | None = None
    payment_method: str | None = None
    note: str | None = None
    location_id: uuid.UUID | None = None


class ExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID | None
    category_name: str | None = None
    ref_no: str | None
    amount_ngn: Decimal
    fx_rate: Decimal | None
    amount_usd: Decimal
    currency: str
    expense_date: date
    payment_method: str | None
    note: str | None
    location_id: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime


class ExpenseListResponse(BaseModel):
    items: list[ExpenseRead]
    total: int
    page: int
    page_size: int
