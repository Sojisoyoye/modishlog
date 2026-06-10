"""Invoice schemes domain Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.invoice_schemes.models import SchemeType


class SchemeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    scheme_type: SchemeType = SchemeType.BLANK
    prefix: str = Field("", max_length=20)
    start_number: int = Field(1, ge=1)
    total_digits: int = Field(5, ge=3, le=8)


class SchemeUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    scheme_type: SchemeType | None = None
    prefix: str | None = Field(None, max_length=20)
    start_number: int | None = Field(None, ge=1)
    total_digits: int | None = Field(None, ge=3, le=8)
    is_active: bool | None = None


class SchemeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    scheme_type: SchemeType
    prefix: str
    start_number: int
    total_digits: int
    next_number: int
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class SchemeListResponse(BaseModel):
    items: list[SchemeRead]
    total: int


class SchemePreview(BaseModel):
    preview: str
