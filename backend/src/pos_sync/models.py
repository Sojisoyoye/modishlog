"""POS sync state — stores watermarks for incremental sync."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, UUIDMixin


class SyncState(UUIDMixin, Base):
    """Key-value store for POS sync watermarks (e.g. sells_max_id).

    Each row is scoped to a specific business via business_id so that
    multi-tenant deployments maintain independent sync watermarks per business.
    The combination of (key, business_id) is unique, preventing PK collisions
    when multiple businesses each need their own 'sells_max_id' watermark.
    """

    __tablename__ = "pos_sync_state"
    __table_args__ = (
        UniqueConstraint("key", "business_id", name="uq_pos_sync_state_key_business"),
    )

    key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, default=None, index=True
    )
