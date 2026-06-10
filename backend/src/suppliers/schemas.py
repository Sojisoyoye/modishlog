"""Suppliers domain Pydantic schemas."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from src.suppliers.models import PayTermType


class SupplierCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    contact_person: str | None = Field(None, max_length=255)
    email: str | None = Field(None, max_length=255)
    mobile: str | None = Field(None, max_length=50)
    alternate_number: str | None = Field(None, max_length=50)
    tax_number: str | None = Field(None, max_length=100)
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    zip_code: str | None = Field(None, max_length=20)
    pay_term_number: int | None = Field(None, ge=1)
    pay_term_type: PayTermType | None = None
    opening_balance: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = None


class SupplierUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    contact_person: str | None = Field(None, max_length=255)
    email: str | None = Field(None, max_length=255)
    mobile: str | None = Field(None, max_length=50)
    alternate_number: str | None = Field(None, max_length=50)
    tax_number: str | None = Field(None, max_length=100)
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    zip_code: str | None = Field(None, max_length=20)
    pay_term_number: int | None = Field(None, ge=1)
    pay_term_type: PayTermType | None = None
    opening_balance: Decimal | None = Field(None, ge=0)
    notes: str | None = None
    is_active: bool | None = None


class SupplierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    contact_person: str | None = None
    email: str | None = None
    mobile: str | None = None
    alternate_number: str | None = None
    tax_number: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    zip_code: str | None = None
    pay_term_number: int | None = None
    pay_term_type: str | None = None
    opening_balance: Decimal = Decimal("0")
    notes: str | None = None
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class SupplierListResponse(BaseModel):
    items: list[SupplierRead]
    total: int


class LedgerEntry(BaseModel):
    date: datetime
    description: str
    debit: Decimal
    credit: Decimal
    balance: Decimal


class ActivityEntry(BaseModel):
    timestamp: datetime
    event_type: str
    description: str
    amount: Decimal | None = None
    reference: str | None = None


class StockReportItem(BaseModel):
    product_id: uuid.UUID
    sku: str
    product_name: str
    quantity_on_hand: int
    unit_cost: Decimal
    stock_value: Decimal
