"""Auth domain SQLAlchemy models."""

import enum
import uuid as _uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base, TimestampMixin, UUIDMixin


class UserRole(str, enum.Enum):
    """Available user roles."""

    ADMIN = "admin"
    SALES_MANAGER = "sales_manager"
    OWNER = "owner"


class Business(UUIDMixin, TimestampMixin, Base):
    """Business entity that owns a set of users."""

    __tablename__ = "businesses"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="NGN")
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    timezone: Mapped[str] = mapped_column(String(60), nullable=False, server_default="Africa/Lagos")
    tax_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fiscal_year_start_month: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # lazy="select" (not "selectin") avoids loading all users whenever a Business is
    # loaded as part of a User query — which would happen on every authenticated request.
    # Call selectinload(Business.users) explicitly only when the full user list is needed.
    users: Mapped[list["User"]] = relationship(back_populates="business", lazy="select")


class User(UUIDMixin, TimestampMixin, Base):
    """User account for authentication and authorization."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, values_callable=lambda x: [e.value for e in x]),
        default=UserRole.ADMIN,
        server_default="admin",
    )
    failed_login_attempts: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(default=None)
    ndpr_consent_given: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    ndpr_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    business_id: Mapped[_uuid.UUID | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    migration_id: Mapped[_uuid.UUID | None] = mapped_column(nullable=True, index=True, default=None)
    business: Mapped["Business | None"] = relationship(back_populates="users", lazy="selectin")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"


class PasswordResetToken(UUIDMixin, TimestampMixin, Base):
    """Token issued for password-reset requests."""

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[_uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(lazy="joined")


class RefreshToken(UUIDMixin, TimestampMixin, Base):
    """Long-lived refresh token stored as a hash."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[_uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    user: Mapped["User"] = relationship(lazy="joined")
