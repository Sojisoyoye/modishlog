"""Auth Pydantic schemas -- request/response validation."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr


class UserRegister(BaseModel):
    """Registration request."""

    email: EmailStr
    password: str
    full_name: str


class UserLogin(BaseModel):
    """Login request."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT token response (includes refresh token on login)."""

    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Logout request -- revokes the refresh token.

    refresh_token is optional: callers that only have a cookie-based session
    (e.g. after a page reload) may omit it; the server still clears the cookie.
    """

    refresh_token: str | None = None


class UserProfile(BaseModel):
    """Public user profile response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    role: str = "admin"
    created_at: datetime


class ForgotPasswordRequest(BaseModel):
    """Forgot-password request -- just an email."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Reset-password request -- token + new password."""

    token: str
    new_password: str


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


class UnlockUserRequest(BaseModel):
    """Admin unlock-account request."""

    email: EmailStr


class UserListItem(BaseModel):
    """Single user record in the admin list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class UserListResponse(BaseModel):
    """Paginated list of users."""

    items: list[UserListItem]
    total: int
    page: int
    page_size: int


class UserInvite(BaseModel):
    """Admin invite-user request."""

    email: EmailStr
    full_name: str
    role: Literal["admin", "sales_manager"] = "sales_manager"
    password: str


class UserUpdate(BaseModel):
    """Admin update-user request — all fields optional."""

    full_name: str | None = None
    role: Literal["admin", "sales_manager"] | None = None
    is_active: bool | None = None


class AdminResetPasswordResponse(BaseModel):
    """Response after admin-initiated password reset."""

    message: str
    token: str
