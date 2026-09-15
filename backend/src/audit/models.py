"""Cross-domain audit trail for sensitive actions (task #246).

Distinct from SaleAuditEntry (sales/models.py), which already tracks
field-level history for a single sale record. AuditLog is the broader,
dispute-oriented trail spanning multiple domains (refunds, user role/
deactivation changes, etc.) -- action + entity_type + entity_id rather
than a per-sale field diff.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, UUIDMixin


class AuditLog(UUIDMixin, Base):
    """Immutable record of a sensitive action. Append-only -- no update or
    delete path is exposed anywhere in this domain."""

    __tablename__ = "audit_logs"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    details: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action}, entity_type={self.entity_type})>"
