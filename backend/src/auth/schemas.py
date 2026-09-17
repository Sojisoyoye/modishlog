"""Auth Pydantic schemas -- request/response validation."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


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
    # Task #252: lets the frontend show the Danger Zone's pending-deletion
    # banner instead of the delete button, without a second round trip.
    business_deletion_requested_at: datetime | None = None
    business_purge_at: datetime | None = None
    # The real business name (auth.Business.name, set at onboarding) --
    # NOT settings.BusinessProfile.business_name, a separate, lazily-
    # created display-profile field that's null until a user explicitly
    # saves the Settings > Business Profile form. The Danger Zone's
    # type-to-confirm check needs a name that's guaranteed to exist.
    business_name: str | None = None
    # Task #240: lets the frontend show a subscription-status banner (trial
    # countdown, past-due warning, read-only notice) without a second round
    # trip. business_trial_ends_at is derived (created_at + 7 days per the
    # billing spec), not stored state -- only meaningful while trialing.
    business_subscription_status: str | None = None
    business_subscription_tier: str | None = None
    business_trial_ends_at: datetime | None = None
    business_current_period_end: datetime | None = None
    business_past_due_since: datetime | None = None


class ForgotPasswordRequest(BaseModel):
    """Forgot-password request -- just an email."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Reset-password request -- token + new password."""

    token: str
    new_password: str


class VerifyEmailRequest(BaseModel):
    """Email-verification request -- just the token."""

    token: str


class ResendVerificationRequest(BaseModel):
    """Resend-verification-email request -- just an email."""

    email: EmailStr


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


class BusinessDeletionResponse(BaseModel):
    """Response for scheduling/cancelling self-service business deletion."""

    message: str
    purge_at: datetime | None


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
    """Response after admin-initiated password reset (task #224).

    Deliberately has no token field -- the raw token is emailed directly
    to the target user, never returned to the admin who initiated it.
    """

    message: str


class OnboardRequest(BaseModel):
    """Public onboarding request — creates a Business and owner User atomically."""

    # Step 1 — Account
    full_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str

    # Step 2 — Business
    business_name: str = Field(..., min_length=2, max_length=255)
    currency: str = Field(default="NGN", min_length=3, max_length=3)
    country: str | None = None
    state: str | None = None
    city: str | None = None
    phone: str | None = None
    timezone: str = "Africa/Lagos"
    tax_number: str | None = None
    fiscal_year_start_month: int = Field(default=1, ge=1, le=12)

    # NDPR consent — required by Nigerian data-protection law
    ndpr_consent: bool

    @field_validator("ndpr_consent")
    @classmethod
    def must_accept_ndpr(cls, v: bool) -> bool:
        if not v:
            raise ValueError("NDPR consent is required to create an account")
        return v


class OnboardResponse(BaseModel):
    """Response after successful business onboarding.

    No session is established here -- self-service signup must verify
    their email (see /auth/verify-email) before their first /auth/login.
    """

    message: str
    user_id: str
    business_id: str
