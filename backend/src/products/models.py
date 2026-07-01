"""Products domain SQLAlchemy models."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base, TimestampMixin, UUIDMixin


class ProductCategory(UUIDMixin, TimestampMixin, Base):
    """Category grouping for products."""

    __tablename__ = "product_categories"

    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("product_categories.id", ondelete="SET NULL"),
        default=None,
        index=True,
    )
    default_margin_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 4), nullable=True, default=None
    )

    products: Mapped[list["Product"]] = relationship(back_populates="category")
    parent: Mapped[Optional["ProductCategory"]] = relationship(
        "ProductCategory",
        foreign_keys="[ProductCategory.parent_id]",
        back_populates="children",
        remote_side="ProductCategory.id",
        lazy="raise",
    )
    children: Mapped[list["ProductCategory"]] = relationship(
        "ProductCategory",
        foreign_keys="[ProductCategory.parent_id]",
        back_populates="parent",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return f"<ProductCategory(id={self.id}, name={self.name})>"


class Product(UUIDMixin, TimestampMixin, Base):
    """Product catalog entry."""

    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(255), index=True)
    sku: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product_categories.id"),
    )
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    selling_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(3), default="NGN")
    is_active: Mapped[bool] = mapped_column(default=True)
    image_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True, default=None
    )
    barcode: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)

    category: Mapped["ProductCategory"] = relationship(back_populates="products")
    price_history: Mapped[list["PriceHistory"]] = relationship(back_populates="product")

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, sku={self.sku})>"


class PriceHistory(UUIDMixin, Base):
    """Audit trail for product price changes."""

    __tablename__ = "price_history"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    old_unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    new_unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    old_selling_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    new_selling_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    reason: Mapped[str | None] = mapped_column(String(500), default=None)
    effective_date: Mapped[date] = mapped_column(Date)
    changed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    product: Mapped["Product"] = relationship(back_populates="price_history")

    def __repr__(self) -> str:
        return f"<PriceHistory(id={self.id}, product_id={self.product_id})>"
