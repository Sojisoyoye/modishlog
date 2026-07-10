"""Suppliers domain SQLAlchemy models."""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base, TimestampMixin, UUIDMixin


class PayTermType(str, enum.Enum):
    DAYS = "days"
    MONTHS = "months"


class Supplier(UUIDMixin, TimestampMixin, Base):
    """A supplier that goods are purchased from."""

    __tablename__ = "suppliers"

    name: Mapped[str] = mapped_column(String(255), index=True)
    contact_person: Mapped[str | None] = mapped_column(String(255), default=None)
    email: Mapped[str | None] = mapped_column(String(255), default=None)
    mobile: Mapped[str | None] = mapped_column(String(50), default=None)
    alternate_number: Mapped[str | None] = mapped_column(String(50), default=None)
    tax_number: Mapped[str | None] = mapped_column(String(100), default=None)
    address_line_1: Mapped[str | None] = mapped_column(String(255), default=None)
    address_line_2: Mapped[str | None] = mapped_column(String(255), default=None)
    city: Mapped[str | None] = mapped_column(String(100), default=None)
    state: Mapped[str | None] = mapped_column(String(100), default=None)
    country: Mapped[str | None] = mapped_column(String(100), default=None)
    zip_code: Mapped[str | None] = mapped_column(String(20), default=None)
    pay_term_number: Mapped[int | None] = mapped_column(Integer, default=None)
    pay_term_type: Mapped[PayTermType | None] = mapped_column(
        Enum(PayTermType, values_callable=lambda x: [e.value for e in x]),
        default=None,
    )
    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0")
    )
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )
    migration_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("migration_jobs.id"), nullable=True, index=True, default=None)

    products: Mapped[list["SupplierProduct"]] = relationship(
        back_populates="supplier", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Supplier(id={self.id}, name={self.name})>"


class SupplierProduct(UUIDMixin, Base):
    """Join table linking a supplier to the products they supply."""

    __tablename__ = "supplier_products"
    __table_args__ = (UniqueConstraint("supplier_id", "product_id"),)

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("suppliers.id", ondelete="CASCADE")
    )
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), default=None)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, default=None)
    migration_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("migration_jobs.id"), nullable=True, index=True, default=None)

    supplier: Mapped["Supplier"] = relationship(back_populates="products")

    def __repr__(self) -> str:
        return (
            f"<SupplierProduct(supplier={self.supplier_id}, product={self.product_id})>"
        )
