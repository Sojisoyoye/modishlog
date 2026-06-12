"""Settings Pydantic schemas."""

from pydantic import BaseModel, Field


class ApiKeyUpsert(BaseModel):
    """Request body for saving an API key."""

    key_name: str = Field(min_length=1, max_length=100)
    key_value: str = Field(min_length=1)


class ApiKeyStatus(BaseModel):
    """Response for API key operations — never returns the plaintext value."""

    key_name: str
    is_configured: bool
