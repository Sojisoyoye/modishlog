"""Products domain Pydantic schemas."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Category schemas
# ---------------------------------------------------------------------------


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    parent_id: Optional[uuid.UUID] = None
    default_margin_pct: Optional[Decimal] = Field(
        default=None, gt=Decimal("0"), lt=Decimal("1")
    )


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    default_margin_pct: Optional[Decimal] = Field(
        default=None, gt=Decimal("0"), lt=Decimal("1")
    )


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    parent_id: Optional[uuid.UUID] = None
    default_margin_pct: Optional[Decimal] = None
    children: list["CategoryRead"] = []


CategoryRead.model_rebuild()


# ---------------------------------------------------------------------------
# Product schemas
# ---------------------------------------------------------------------------


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    sku: str | None = None
    description: str | None = None
    category_id: uuid.UUID | None = None
    unit_cost: Decimal = Field(..., gt=Decimal("0"))
    selling_price: Decimal = Field(..., gt=Decimal("0"))
    currency: str = "NGN"


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category_id: uuid.UUID | None = None
    unit_cost: Decimal | None = Field(default=None, gt=Decimal("0"))
    selling_price: Decimal | None = Field(default=None, gt=Decimal("0"))
    image_url: str | None = None


class ProductVariantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sku: str | None = None
    barcode: str | None = None
    attributes: dict = {}
    price_override: Decimal | None = Field(default=None, gt=0)
    cost_price_override: Decimal | None = Field(default=None, gt=0)


class ProductVariantUpdate(BaseModel):
    name: str | None = None
    sku: str | None = None
    barcode: str | None = None
    attributes: dict | None = None
    price_override: Decimal | None = Field(default=None, gt=0)
    cost_price_override: Decimal | None = Field(default=None, gt=0)
    is_active: bool | None = None


class ProductVariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    business_id: uuid.UUID
    name: str
    sku: str | None
    barcode: str | None
    attributes: dict
    price_override: Decimal | None
    cost_price_override: Decimal | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    sku: str
    slug: str
    description: str | None = None
    category_id: uuid.UUID | None = None
    unit_cost: Decimal
    selling_price: Decimal
    currency: str
    is_active: bool
    image_url: str | None = None
    has_variants: bool = False
    variants: list[ProductVariantRead] = []
    created_at: datetime
    updated_at: datetime


class ProductListResponse(BaseModel):
    items: list[ProductRead]
    total: int
    page: int
    page_size: int


class BulkUploadRowError(BaseModel):
    row: int
    error: str


class BulkProductUploadResponse(BaseModel):
    total_rows: int
    successful: int
    failed: int
    errors: list[BulkUploadRowError]
    created_ids: list[uuid.UUID]


# ---------------------------------------------------------------------------
# Price history schemas
# ---------------------------------------------------------------------------


class PriceHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    old_unit_cost: Decimal
    new_unit_cost: Decimal
    old_selling_price: Decimal
    new_selling_price: Decimal
    reason: str | None = None
    effective_date: date
    changed_by: uuid.UUID
