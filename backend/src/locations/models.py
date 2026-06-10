"""Locations domain SQLAlchemy models."""

import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin


class BusinessLocation(UUIDMixin, TimestampMixin, Base):
    """A physical or virtual business location."""

    __tablename__ = "business_locations"

    name: Mapped[str] = mapped_column(String(255), index=True)
    location_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    mobile: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    alternate_number: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    landmark: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    def __repr__(self) -> str:
        return f"<BusinessLocation(id={self.id}, name={self.name}, code={self.location_code})>"
