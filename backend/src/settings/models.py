"""Settings domain — user-scoped API keys and preferences."""

import uuid as _uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin


class UserApiKey(UUIDMixin, TimestampMixin, Base):
    """Per-user API key stored encrypted with Fernet."""

    __tablename__ = "user_api_keys"

    user_id: Mapped[_uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    key_name: Mapped[str] = mapped_column(String(100))
    encrypted_value: Mapped[str] = mapped_column(Text)


class UserPreferences(UUIDMixin, TimestampMixin, Base):
    """Per-user preference store — one row per user."""

    __tablename__ = "user_preferences"

    user_id: Mapped[_uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    fiscal_year_start_month: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )
    fiscal_year_start_day: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )


class BusinessProfile(UUIDMixin, TimestampMixin, Base):
    """Single-row table storing the business's public profile and defaults."""

    __tablename__ = "business_profile"

    business_name: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    address_line_1: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    address_line_2: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    tax_number: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    registration_number: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="NGN", server_default="NGN")
    timezone: Mapped[str] = mapped_column(String(60), nullable=False, default="Africa/Lagos", server_default="Africa/Lagos")
    updated_by: Mapped[_uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, default=None
    )


class AppSetting(Base):
    """Global key-value store for application-wide settings."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    updated_by: Mapped[_uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, default=None
    )
