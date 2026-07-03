"""Invoice schemes domain SQLAlchemy models."""

import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin


class SchemeType(str, enum.Enum):
    BLANK = "blank"
    YEAR = "year"


class InvoiceScheme(UUIDMixin, TimestampMixin, Base):
    """An invoice numbering scheme configuration."""

    __tablename__ = "invoice_schemes"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    scheme_type: Mapped[SchemeType] = mapped_column(
        Enum(SchemeType, values_callable=lambda x: [e.value for e in x]),
        default=SchemeType.BLANK,
    )
    prefix: Mapped[str] = mapped_column(String(20), default="")
    start_number: Mapped[int] = mapped_column(Integer, default=1)
    total_digits: Mapped[int] = mapped_column(Integer, default=5)
    next_number: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    def __repr__(self) -> str:
        return f"<InvoiceScheme(id={self.id}, name={self.name})>"
