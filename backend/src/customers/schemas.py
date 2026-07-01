"""Customers domain Pydantic schemas."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.suppliers.models import PayTermType


class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    contact_number: str | None = Field(None, max_length=50)
    alternate_number: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)
    address: str | None = None
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=100)
    zip_code: str | None = Field(None, max_length=20)
    tax_number: str | None = Field(None, max_length=100)
    pay_term_number: int | None = Field(None, ge=1)
    pay_term_type: PayTermType | None = None
    opening_balance: Decimal = Field(Decimal("0"), ge=0)
    credit_limit: Decimal | None = Field(None, ge=0)
    is_active: bool = True
    customer_group: str | None = Field(None, max_length=100)
    notes: str | None = None


class CustomerUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    contact_number: str | None = Field(None, max_length=50)
    alternate_number: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)
    address: str | None = None
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=100)
    zip_code: str | None = Field(None, max_length=20)
    tax_number: str | None = Field(None, max_length=100)
    pay_term_number: int | None = Field(None, ge=1)
    pay_term_type: PayTermType | None = None
    opening_balance: Decimal | None = Field(None, ge=0)
    credit_limit: Decimal | None = Field(None, ge=0)
    is_active: bool | None = None
    customer_group: str | None = Field(None, max_length=100)
    notes: str | None = None

    @field_validator("opening_balance", "is_active", mode="before")
    @classmethod
    def _reject_explicit_null(cls, v: object) -> object:
        if v is None:
            raise ValueError("cannot be set to null")
        return v


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    contact_number: str | None = None
    alternate_number: str | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    zip_code: str | None = None
    tax_number: str | None = None
    pay_term_number: int | None = None
    pay_term_type: PayTermType | None = None
    opening_balance: Decimal
    credit_limit: Decimal | None = None
    is_active: bool
    customer_group: str | None = None
    notes: str | None = None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CustomerListResponse(BaseModel):
    items: list[CustomerRead]
    total: int
