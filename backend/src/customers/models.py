"""Customers domain SQLAlchemy models."""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin


class Customer(UUIDMixin, TimestampMixin, Base):
    """A saved customer that can be associated with sales."""

    __tablename__ = "customers"

    name: Mapped[str] = mapped_column(String(255), index=True)
    contact_number: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    address: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    def __repr__(self) -> str:
        return f"<Customer(id={self.id}, name={self.name})>"
