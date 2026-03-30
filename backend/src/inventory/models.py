"""Inventory domain SQLAlchemy models."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin


class MovementType(str, enum.Enum):
    """Types of stock movements."""

    SALE_DEPLETION = "sale_depletion"
    SALE_REVERSAL = "sale_reversal"
    MANUAL_ADD = "manual_add"
    MANUAL_REMOVE = "manual_remove"
    ORDER_RECEIVED = "order_received"
    DAMAGED = "damaged"


class AlertStatus(str, enum.Enum):
    """Status for low-stock alerts."""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class InventoryLevel(UUIDMixin, TimestampMixin, Base):
    """Current stock level for a product (one row per product)."""

    __tablename__ = "inventory_levels"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"), unique=True
    )
    quantity_on_hand: Mapped[int] = mapped_column(Integer, default=0)
    quantity_reserved: Mapped[int] = mapped_column(Integer, default=0)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=10)
    last_replenished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    def __repr__(self) -> str:
        return f"<InventoryLevel(product_id={self.product_id}, on_hand={self.quantity_on_hand})>"


class StockMovement(UUIDMixin, Base):
    """Immutable record of a stock quantity change."""

    __tablename__ = "stock_movements"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    movement_type: Mapped[MovementType] = mapped_column(Enum(MovementType))
    quantity_change: Mapped[int] = mapped_column(Integer)
    quantity_before: Mapped[int] = mapped_column(Integer)
    quantity_after: Mapped[int] = mapped_column(Integer)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    reference_type: Mapped[str | None] = mapped_column(String(50), default=None)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    performed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    def __repr__(self) -> str:
        return f"<StockMovement(id={self.id}, type={self.movement_type})>"


class LowStockAlert(UUIDMixin, Base):
    """Alert raised when a product drops below its low-stock threshold."""

    __tablename__ = "low_stock_alerts"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    threshold: Mapped[int] = mapped_column(Integer)
    current_quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus), default=AlertStatus.ACTIVE
    )
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    def __repr__(self) -> str:
        return f"<LowStockAlert(id={self.id}, product_id={self.product_id})>"
