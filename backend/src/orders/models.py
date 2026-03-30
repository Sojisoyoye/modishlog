"""Orders domain SQLAlchemy models."""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base, TimestampMixin, UUIDMixin


class OrderStatus(str, enum.Enum):
    """Purchase order lifecycle status."""

    PENDING = "Pending"
    IN_PRODUCTION = "In Production"
    SHIPPING = "Shipping"
    CLEARED = "Cleared"
    DELIVERED = "Delivered"
    CANCELLED = "Cancelled"


class PaymentMethod(str, enum.Enum):
    """Payment method for order payments."""

    BANK_TRANSFER = "bank_transfer"
    LC = "lc"
    CASH = "cash"


class PaymentStatus(str, enum.Enum):
    """Payment record status."""

    COMPLETED = "completed"
    VOIDED = "voided"


class PurchaseOrder(UUIDMixin, TimestampMixin, Base):
    """Purchase order from a supplier."""

    __tablename__ = "purchase_orders"

    order_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    supplier_name: Mapped[str] = mapped_column(String(255))
    supplier_contact: Mapped[str | None] = mapped_column(String(255), default=None)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), default=OrderStatus.PENDING
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    fx_rate_at_creation: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), default=None
    )
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, default=None)
    actual_delivery_date: Mapped[date | None] = mapped_column(Date, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    line_items: Mapped[list["OrderLineItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    payments: Mapped[list["OrderPayment"]] = relationship(back_populates="order")
    status_history: Mapped[list["OrderStatusHistory"]] = relationship(
        back_populates="order"
    )

    def __repr__(self) -> str:
        return f"<PurchaseOrder(id={self.id}, number={self.order_number})>"


class OrderLineItem(UUIDMixin, Base):
    """Line item within a purchase order."""

    __tablename__ = "order_line_items"

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_orders.id"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    order: Mapped["PurchaseOrder"] = relationship(back_populates="line_items")

    def __repr__(self) -> str:
        return f"<OrderLineItem(id={self.id}, order_id={self.order_id})>"


class OrderStatusHistory(UUIDMixin, Base):
    """Immutable log of purchase order status transitions."""

    __tablename__ = "order_status_history"

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_orders.id"))
    from_status: Mapped[str | None] = mapped_column(String(50), default=None)
    to_status: Mapped[str] = mapped_column(String(50))
    transitioned_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    order: Mapped["PurchaseOrder"] = relationship(back_populates="status_history")

    def __repr__(self) -> str:
        return f"<OrderStatusHistory(id={self.id}, to={self.to_status})>"


class OrderPayment(UUIDMixin, Base):
    """Payment record against a purchase order."""

    __tablename__ = "order_payments"

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_orders.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(3))
    payment_date: Mapped[date] = mapped_column(Date)
    payment_method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod))
    reference: Mapped[str | None] = mapped_column(String(255), default=None)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), default=PaymentStatus.COMPLETED
    )
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    order: Mapped["PurchaseOrder"] = relationship(back_populates="payments")

    def __repr__(self) -> str:
        return f"<OrderPayment(id={self.id}, order_id={self.order_id})>"
