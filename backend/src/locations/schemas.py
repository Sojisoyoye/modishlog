"""Locations domain Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LocationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    location_code: str = Field(..., min_length=1, max_length=20)
    mobile: str | None = Field(None, max_length=50)
    alternate_number: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)
    website: str | None = Field(None, max_length=255)
    landmark: str | None = Field(None, max_length=255)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=100)
    zip_code: str | None = Field(None, max_length=20)


class LocationUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    location_code: str | None = Field(None, min_length=1, max_length=20)
    mobile: str | None = Field(None, max_length=50)
    alternate_number: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)
    website: str | None = Field(None, max_length=255)
    landmark: str | None = Field(None, max_length=255)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    country: str | None = Field(None, max_length=100)
    zip_code: str | None = Field(None, max_length=20)
    is_active: bool | None = None


class LocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    location_code: str
    mobile: str | None = None
    alternate_number: str | None = None
    email: str | None = None
    website: str | None = None
    landmark: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    zip_code: str | None = None
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class LocationListResponse(BaseModel):
    items: list[LocationRead]
    total: int
