"""Stock count domain models."""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

from src.core.database import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from src.products.models import Product


class StockCountStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    FINALIZED = "FINALIZED"


class StockCountType(str, enum.Enum):
    PRODUCT = "PRODUCT"
    LOT = "LOT"


class StockCount(UUIDMixin, TimestampMixin, Base):
    """Header record for a physical stock count session."""

    __tablename__ = "stock_counts"

    count_date: Mapped[date] = mapped_column(Date, nullable=False)
    count_type: Mapped[StockCountType] = mapped_column(
        Enum(
            StockCountType,
            values_callable=lambda x: [e.value for e in x],
            name="stockcounttype",
        ),
        nullable=False,
    )
    status: Mapped[StockCountStatus] = mapped_column(
        Enum(
            StockCountStatus,
            values_callable=lambda x: [e.value for e in x],
            name="stockcountstatus",
        ),
        default=StockCountStatus.DRAFT,
        nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, default=None)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    finalized_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=None
    )

    items: Mapped[list["StockCountItem"]] = relationship(
        back_populates="stock_count", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<StockCount(id={self.id}, type={self.count_type}, status={self.status})>"
        )


class StockCountItem(UUIDMixin, Base):
    """One line in a stock count session — one product or one lot."""

    __tablename__ = "stock_count_items"

    stock_count_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stock_counts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    order_line_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("order_line_items.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    # Null until finalization — snapshotted from live stock at finalize time
    system_quantity_at_count: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 6), nullable=True, default=None
    )
    counted_quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 6), nullable=True, default=None
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, default=None)

    stock_count: Mapped["StockCount"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(  # type: ignore[name-defined]
        "Product", foreign_keys=[product_id], lazy="raise", viewonly=True
    )

    @property
    def product_name(self) -> str:
        return self.product.name  # accessed only when selectinloaded

    def __repr__(self) -> str:
        return f"<StockCountItem(id={self.id}, product={self.product_id})>"
