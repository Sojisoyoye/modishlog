"""Customers domain SQLAlchemy models."""

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin
from src.suppliers.models import PayTermType


class Customer(UUIDMixin, TimestampMixin, Base):
    """A saved customer that can be associated with sales."""

    __tablename__ = "customers"

    name: Mapped[str] = mapped_column(String(255), index=True)
    contact_number: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    alternate_number: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    address: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    country: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None
    )
    zip_code: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=None
    )
    tax_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None
    )
    pay_term_number: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )
    pay_term_type: Mapped[PayTermType | None] = mapped_column(
        Enum(
            PayTermType,
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        nullable=True,
        default=None,
    )
    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    credit_limit: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True, default=None
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    customer_group: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    def __repr__(self) -> str:
        return f"<Customer(id={self.id}, name={self.name})>"
