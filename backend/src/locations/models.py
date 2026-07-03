"""Locations domain SQLAlchemy models."""

import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin


class LocationType(str, enum.Enum):
    RETAIL = "retail"
    WAREHOUSE = "warehouse"
    ONLINE = "online"


class BusinessLocation(UUIDMixin, TimestampMixin, Base):
    """A physical or virtual business location."""

    __tablename__ = "business_locations"
    __table_args__ = (
        UniqueConstraint(
            "location_code",
            "business_id",
            name="uq_business_locations_code_business",
        ),
    )

    name: Mapped[str] = mapped_column(String(255), index=True)
    location_code: Mapped[str] = mapped_column(String(20), index=True)
    mobile: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    alternate_number: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    website: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    landmark: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    city: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    country: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None
    )
    zip_code: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=None
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )
    timezone: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        default="Africa/Lagos",
        server_default="Africa/Lagos",
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="NGN", server_default="NGN"
    )
    tax_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None
    )
    location_type: Mapped[LocationType | None] = mapped_column(
        Enum(LocationType, values_callable=lambda x: [e.value for e in x], create_type=False),
        nullable=True,
        default=None,
    )
    is_pos_location: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    pos_location_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )

    def __repr__(self) -> str:
        return f"<BusinessLocation(id={self.id}, name={self.name}, code={self.location_code})>"
