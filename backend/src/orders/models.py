"""Orders domain SQLAlchemy models."""

import enum
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from src.suppliers.models import Supplier

from src.core.database import Base, TimestampMixin, UUIDMixin


class OrderStatus(str, enum.Enum):
    """Purchase order lifecycle status."""

    ORDERED = "ORDERED"  # PO sent to supplier, no stock impact yet
    PENDING = "PENDING"
    IN_PRODUCTION = "IN_PRODUCTION"
    SHIPPING = "SHIPPING"
    CLEARED = "CLEARED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class PayTermType(str, enum.Enum):
    DAYS = "days"
    MONTHS = "months"


class DiscountType(str, enum.Enum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"


class PaymentMethod(str, enum.Enum):
    """Payment method for order payments."""

    BANK_TRANSFER = "BANK_TRANSFER"
    LC = "LC"
    CASH = "CASH"


class PaymentStatus(str, enum.Enum):
    """Payment record status."""

    COMPLETED = "COMPLETED"
    VOIDED = "VOIDED"


class OrderPaymentStatus(str, enum.Enum):
    """Payment status of a purchase order."""

    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    PAID = "PAID"


class PurchaseOrder(UUIDMixin, TimestampMixin, Base):
    """Purchase order from a supplier."""

    __tablename__ = "purchase_orders"

    business_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True, default=None
    )
    order_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"), default=None, index=True
    )
    supplier_name: Mapped[str] = mapped_column(String(255))
    supplier_contact: Mapped[str | None] = mapped_column(String(255), default=None)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, values_callable=lambda x: [e.value for e in x]),
        default=OrderStatus.PENDING,
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    fx_rate_at_creation: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), default=None
    )
    fx_rate_at_delivery: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), default=None
    )
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, default=None)
    actual_delivery_date: Mapped[date | None] = mapped_column(Date, default=None)
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    clearing_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    # PO vs received purchase distinction
    is_purchase_order: Mapped[bool] = mapped_column(Boolean, default=False)

    # Payment terms (auto-populated from supplier)
    pay_term_number: Mapped[int | None] = mapped_column(Integer, default=None)
    pay_term_type: Mapped[PayTermType | None] = mapped_column(
        Enum(
            PayTermType,
            values_callable=lambda x: [e.value for e in x],
            name="paytermtype_orders",
        ),
        default=None,
    )

    # Shipping details
    shipping_details: Mapped[str | None] = mapped_column(Text, default=None)
    shipping_custom_field_1: Mapped[str | None] = mapped_column(
        String(255), default=None
    )
    shipping_custom_field_2: Mapped[str | None] = mapped_column(
        String(255), default=None
    )
    shipping_custom_field_3: Mapped[str | None] = mapped_column(
        String(255), default=None
    )
    shipping_custom_field_4: Mapped[str | None] = mapped_column(
        String(255), default=None
    )
    shipping_custom_field_5: Mapped[str | None] = mapped_column(
        String(255), default=None
    )

    # Additional expenses (customs, insurance, etc.)
    additional_expense_key_1: Mapped[str | None] = mapped_column(
        String(100), default=None
    )
    additional_expense_value_1: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), default=None
    )
    additional_expense_key_2: Mapped[str | None] = mapped_column(
        String(100), default=None
    )
    additional_expense_value_2: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), default=None
    )
    additional_expense_key_3: Mapped[str | None] = mapped_column(
        String(100), default=None
    )
    additional_expense_value_3: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), default=None
    )
    additional_expense_key_4: Mapped[str | None] = mapped_column(
        String(100), default=None
    )
    additional_expense_value_4: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), default=None
    )

    # Invoice-level discount
    discount_type: Mapped[DiscountType | None] = mapped_column(
        Enum(
            DiscountType,
            values_callable=lambda x: [e.value for e in x],
            name="discounttype",
        ),
        default=None,
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0")
    )

    # Invoice-level tax
    tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), default=None)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))

    # Supplier invoice reference
    supplier_invoice_number: Mapped[str | None] = mapped_column(
        String(100), default=None
    )
    supplier_invoice_date: Mapped[date | None] = mapped_column(Date, default=None)

    # Order date, payment status, and location
    order_date: Mapped[date | None] = mapped_column(Date, default=None)
    payment_status: Mapped[OrderPaymentStatus] = mapped_column(
        Enum(
            OrderPaymentStatus,
            values_callable=lambda x: [e.value for e in x],
            name="order_payment_status",
        ),
        default=OrderPaymentStatus.UNPAID,
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("business_locations.id", ondelete="SET NULL"),
        default=None,
        index=True,
    )
    pos_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None, index=True
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )
    migration_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("migration_jobs.id"), nullable=True, index=True, default=None)

    line_items: Mapped[list["OrderLineItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    payments: Mapped[list["OrderPayment"]] = relationship(back_populates="order")
    status_history: Mapped[list["OrderStatusHistory"]] = relationship(
        back_populates="order"
    )
    supplier: Mapped["Supplier | None"] = relationship(
        "Supplier", foreign_keys=[supplier_id], lazy="raise", viewonly=True
    )

    def __repr__(self) -> str:
        return f"<PurchaseOrder(id={self.id}, number={self.order_number})>"


class OrderLineItem(UUIDMixin, Base):
    """Line item within a purchase order."""

    __tablename__ = "order_line_items"

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_orders.id"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    # variant_id: if set, this line item is for a specific product variant.
    # Unit 1's migration adds this column; ORM declaration here allows service code
    # to set it before the migration is applied.
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_variants.id"), nullable=True, default=None, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    unit_cost_ngn: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), default=None)
    sell_price_ngn: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), default=None)
    units_remaining: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), default=None
    )
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    migration_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("migration_jobs.id"), nullable=True, index=True, default=None)

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
    migration_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("migration_jobs.id"), nullable=True, index=True, default=None)

    order: Mapped["PurchaseOrder"] = relationship(back_populates="status_history")

    def __repr__(self) -> str:
        return f"<OrderStatusHistory(id={self.id}, to={self.to_status})>"


class OrderPayment(UUIDMixin, Base):
    """Payment record against a purchase order."""

    __tablename__ = "order_payments"

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_orders.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(3))
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), default=None)
    payment_date: Mapped[date] = mapped_column(Date)
    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, values_callable=lambda x: [e.value for e in x])
    )
    reference: Mapped[str | None] = mapped_column(String(255), default=None)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, values_callable=lambda x: [e.value for e in x]),
        default=PaymentStatus.COMPLETED,
    )
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    migration_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("migration_jobs.id"), nullable=True, index=True, default=None)

    order: Mapped["PurchaseOrder"] = relationship(back_populates="payments")

    def __repr__(self) -> str:
        return f"<OrderPayment(id={self.id}, order_id={self.order_id})>"


class PurchaseReturn(UUIDMixin, TimestampMixin, Base):
    """Return of goods against a received purchase order."""

    __tablename__ = "purchase_returns"

    original_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("purchase_orders.id"), index=True
    )
    ref_no: Mapped[str | None] = mapped_column(String(100), default=None)
    return_date: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0"), server_default="0"
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )

    original_order: Mapped["PurchaseOrder"] = relationship(
        "PurchaseOrder", foreign_keys=[original_order_id], lazy="raise", viewonly=True
    )

    def __repr__(self) -> str:
        return f"<PurchaseReturn(id={self.id}, order={self.original_order_id})>"


class LotConsumption(UUIDMixin, Base):
    """Ledger of exactly which OrderLineItem lot rows a sale's
    _deduct_lot_units() call consumed, and how much of each.

    _deduct_lot_units() (src/sales/service.py) decrements
    OrderLineItem.units_remaining with no other record of the
    transaction — voiding a sale could only guess which lots to credit
    back, or simply didn't try, silently leaving lots permanently short.
    This table lets void_sale() reverse a sale's lot consumption exactly
    instead of guessing — mirrors FifoConsumption (src/inventory/models.py,
    task 166) for the parallel units_remaining ledger (task 168).

    Both sale_id and order_line_item_id cascade-delete: a consumption
    record is meaningless once either side of the transaction it
    describes is gone.
    """

    __tablename__ = "lot_consumptions"

    sale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales.id", ondelete="CASCADE"), index=True
    )
    order_line_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("order_line_items.id", ondelete="CASCADE"), index=True
    )
    quantity_consumed: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return (
            f"<LotConsumption(sale_id={self.sale_id}, "
            f"order_line_item_id={self.order_line_item_id}, "
            f"quantity_consumed={self.quantity_consumed})>"
        )
