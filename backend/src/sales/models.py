"""Sales domain SQLAlchemy models."""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin


class SaleStatus(str, enum.Enum):
    """Sale record status."""

    COMPLETED = "completed"
    VOIDED = "voided"
    PENDING = "pending"


class SaleChannel(str, enum.Enum):
    """Sales channel."""

    ONLINE = "online"
    RETAIL = "retail"
    WHOLESALE = "wholesale"


class UploadJobStatus(str, enum.Enum):
    """Status for bulk upload jobs."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class Sale(UUIDMixin, TimestampMixin, Base):
    """Individual sale transaction record."""

    __tablename__ = "sales"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(3), default="NGN")
    sale_date: Mapped[date] = mapped_column(Date, index=True)
    channel: Mapped[SaleChannel] = mapped_column(Enum(SaleChannel))
    status: Mapped[SaleStatus] = mapped_column(
        Enum(SaleStatus), default=SaleStatus.COMPLETED
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True, index=True, default=None
    )
    discount_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True, default=None
    )
    fifo_cogs: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True, default=None
    )
    fifo_gross_profit: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True, default=None
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True, default=None
    )
    customer_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    contact_number: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    payment_method: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    payment_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default="paid"
    )
    payment_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True, default=None
    )
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("business_locations.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<Sale(id={self.id}, product_id={self.product_id}, total={self.total_amount})>"


class SaleBulkUploadJob(UUIDMixin, Base):
    """Tracks a CSV/Excel bulk upload of sales data."""

    __tablename__ = "sale_bulk_upload_jobs"

    filename: Mapped[str] = mapped_column(String(500))
    status: Mapped[UploadJobStatus] = mapped_column(
        Enum(UploadJobStatus), default=UploadJobStatus.PENDING
    )
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    processed_rows: Mapped[int] = mapped_column(Integer, default=0)
    successful_rows: Mapped[int] = mapped_column(Integer, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0)
    error_details: Mapped[dict | None] = mapped_column(JSON, default=None)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    def __repr__(self) -> str:
        return f"<SaleBulkUploadJob(id={self.id}, status={self.status})>"


class SaleAuditEntry(UUIDMixin, Base):
    """Immutable audit log for sale record changes."""

    __tablename__ = "sale_audit_entries"

    sale_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales.id"))
    action: Mapped[str] = mapped_column(String(50))
    field_changes: Mapped[dict | None] = mapped_column(JSON, default=None)
    performed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<SaleAuditEntry(id={self.id}, sale_id={self.sale_id}, action={self.action})>"


class SellReturn(UUIDMixin, TimestampMixin, Base):
    """Return of goods against a completed sale."""

    __tablename__ = "sell_returns"

    sale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales.id", ondelete="CASCADE"), index=True
    )
    return_date: Mapped[date] = mapped_column(Date)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0"), server_default="0"
    )
    ref_no: Mapped[str | None] = mapped_column(String(100), default=None, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    def __repr__(self) -> str:
        return f"<SellReturn(id={self.id}, sale_id={self.sale_id}, amount={self.total_amount})>"
