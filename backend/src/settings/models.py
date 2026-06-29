"""Settings domain — user-scoped API keys and preferences."""

import uuid as _uuid

from sqlalchemy import ForeignKey, Integer, String, Text
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
