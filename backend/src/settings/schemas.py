"""Settings Pydantic schemas."""

import calendar
from typing import Optional

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

    fiscal_year_start_month: Optional[int] = Field(None, ge=1, le=12)
    fiscal_year_start_day: Optional[int] = Field(None, ge=1, le=31)

    @model_validator(mode="after")
    def both_or_neither_and_valid_date(self) -> "FiscalYearUpdate":
        month = self.fiscal_year_start_month
        day = self.fiscal_year_start_day
        if (month is None) != (day is None):
            raise ValueError(
                "fiscal_year_start_month and fiscal_year_start_day must both be set or both be null"
            )
        if month is not None and day is not None:
            max_day = calendar.monthrange(2000, month)[1]
            if day > max_day:
                raise ValueError(
                    f"fiscal_year_start_day {day} is invalid for month {month} "
                    f"(max {max_day})"
                )
        return self


class FiscalYearRead(BaseModel):
    """Response for fiscal year start setting."""

    model_config = ConfigDict(from_attributes=True)

    fiscal_year_start_month: Optional[int]
    fiscal_year_start_day: Optional[int]
