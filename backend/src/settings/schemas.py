"""Settings Pydantic schemas."""

import calendar
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApiKeyUpsert(BaseModel):
    """Request body for saving an API key."""

    key_name: str = Field(min_length=1, max_length=100)
    key_value: str = Field(min_length=1)


class ApiKeyStatus(BaseModel):
    """Response for API key operations — never returns the plaintext value."""

    key_name: str
    is_configured: bool


class FiscalYearUpdate(BaseModel):
    """Request body for setting fiscal year start."""

    fiscal_year_start_month: int | None = Field(None, ge=1, le=12)
    fiscal_year_start_day: int | None = Field(None, ge=1, le=31)

    @model_validator(mode="after")
    def both_or_neither_and_valid_date(self) -> "FiscalYearUpdate":
        month = self.fiscal_year_start_month
        day = self.fiscal_year_start_day
        if (month is None) != (day is None):
            raise ValueError(
                "fiscal_year_start_month and fiscal_year_start_day must both be set or both be null"
            )
        if month is not None and day is not None:
            # Use a non-leap year so Feb is capped at 28, preventing Feb 29 from
            # being stored (date(non_leap_year, 2, 29) raises ValueError at runtime).
            max_day = calendar.monthrange(2001, month)[1]
            if day > max_day:
                raise ValueError(
                    f"fiscal_year_start_day {day} is invalid for month {month} "
                    f"(max {max_day})"
                )
        return self


class FiscalYearRead(BaseModel):
    """Response for fiscal year start setting."""

    model_config = ConfigDict(from_attributes=True)

    fiscal_year_start_month: int | None
    fiscal_year_start_day: int | None


class BusinessProfileUpdate(BaseModel):
    business_name: str | None = None
    address_line_1: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    zip_code: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    tax_number: str | None = None
    registration_number: str | None = None
    currency: str | None = None
    timezone: str | None = None


class BusinessProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_name: str | None
    address_line_1: str | None
    city: str | None
    state: str | None
    country: str | None
    zip_code: str | None
    phone: str | None
    email: str | None
    website: str | None
    tax_number: str | None
    registration_number: str | None
    currency: str
    timezone: str
    updated_at: datetime


class AppSettingRead(BaseModel):
    key: str
    value: str | None


class AppSettingWrite(BaseModel):
    value: str | None = None


class ApiKeyTestResult(BaseModel):
    success: bool
    message: str
    latency_ms: int | None = None
