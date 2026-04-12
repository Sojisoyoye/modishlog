"""Auth domain SQLAlchemy models."""

import enum
import uuid as _uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base, TimestampMixin, UUIDMixin


class UserRole(str, enum.Enum):
    """Available user roles."""

    ADMIN = "admin"
    SALES_MANAGER = "sales_manager"


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
