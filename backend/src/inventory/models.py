"""Inventory domain SQLAlchemy models."""

import enum
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    column,
    func,
)
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
    STOCK_ADJUSTMENT = "stock_adjustment"
    OPENING_STOCK = "opening_stock"


class AlertStatus(str, enum.Enum):
    """Status for low-stock alerts."""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class InventoryLevel(UUIDMixin, TimestampMixin, Base):
    """Current stock level for a product or product variant.

    One row per (product_id, variant_id) pair. When variant_id is NULL the row
    tracks the product's aggregate / non-variant stock.
    """

    __tablename__ = "inventory_levels"
    # A plain UNIQUE(product_id, variant_id) constraint would NOT prevent
    # two variant_id=NULL rows for the same product — Postgres treats NULLs
    # as distinct for uniqueness purposes. Two partial unique indexes
    # express what's actually wanted: at most one aggregate (variant_id
    # NULL) row per product, and at most one row per real (product_id,
    # variant_id) pair.
    __table_args__ = (
        Index(
            "uq_inventory_levels_product_no_variant",
            "product_id",
            unique=True,
            postgresql_where=column("variant_id").is_(None),
        ),
        Index(
            "uq_inventory_levels_product_variant",
            "product_id",
            "variant_id",
            unique=True,
            postgresql_where=column("variant_id").is_not(None),
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    # variant_id is NULL for products without variants (or the aggregate row).
    # Unit 1's migration adds this column; we define it here so ORM queries compile.
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_variants.id"), nullable=True, default=None, index=True
    )
    quantity_on_hand: Mapped[int] = mapped_column(Integer, default=0)
    quantity_reserved: Mapped[int] = mapped_column(Integer, default=0)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=10)
    last_replenished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    migration_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("migration_jobs.id"), nullable=True, index=True, default=None)

    def __repr__(self) -> str:
        return f"<InventoryLevel(product_id={self.product_id}, variant_id={self.variant_id}, on_hand={self.quantity_on_hand})>"


class StockMovement(UUIDMixin, Base):
    """Immutable record of a stock quantity change."""

    __tablename__ = "stock_movements"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    # variant_id links the movement to a specific variant row.
    # Unit 1's migration adds this column; ORM column declared here for service use.
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_variants.id"), nullable=True, default=None, index=True
    )
    movement_type: Mapped[MovementType] = mapped_column(Enum(MovementType))
    quantity_change: Mapped[int] = mapped_column(Integer)
    quantity_before: Mapped[int] = mapped_column(Integer)
    quantity_after: Mapped[int] = mapped_column(Integer)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    reference_type: Mapped[str | None] = mapped_column(String(50), default=None)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    performed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    migration_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("migration_jobs.id"), nullable=True, index=True, default=None)

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


class InventoryBatch(UUIDMixin, Base):
    """A batch of inventory received from a purchase order.

    Tracks quantity remaining for FIFO cost matching on sales.
    landed_cost_per_unit = (unit_cost_usd × fx_rate_at_arrival) + logistics_allocation_per_unit
    """

    __tablename__ = "inventory_batches"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("purchase_orders.id"), index=True
    )
    quantity_received: Mapped[int] = mapped_column(Integer)
    quantity_remaining: Mapped[int] = mapped_column(Integer)
    unit_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    fx_rate_at_arrival: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    logistics_allocation_per_unit: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0")
    )
    landed_cost_per_unit: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    received_at: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    migration_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("migration_jobs.id"), nullable=True, index=True, default=None)

    def __repr__(self) -> str:
        return f"<InventoryBatch(id={self.id}, product_id={self.product_id}, remaining={self.quantity_remaining})>"
