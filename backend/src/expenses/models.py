import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base, MigrationTaggedMixin, TimestampMixin, UUIDMixin


class ExpenseCategory(UUIDMixin, MigrationTaggedMixin, TimestampMixin, Base):
    __tablename__ = "expense_categories"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    expenses: Mapped[list["Expense"]] = relationship(
        "Expense", back_populates="category", lazy="raise"
    )


class Expense(UUIDMixin, MigrationTaggedMixin, TimestampMixin, Base):
    __tablename__ = "expenses"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("expense_categories.id"), nullable=True
    )
    ref_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    amount_ngn: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    expense_date: Mapped[date] = mapped_column(Date, index=True)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("business_locations.id"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    category: Mapped["ExpenseCategory | None"] = relationship(
        "ExpenseCategory", back_populates="expenses", lazy="raise"
    )
