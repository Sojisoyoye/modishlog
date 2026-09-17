"""Billing domain models (task #239) -- webhook idempotency guard."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, UUIDMixin


class WebhookEvent(UUIDMixin, Base):
    """Record of a processed gateway webhook event -- the idempotency guard
    against redelivery (task #239). A row existing for a given
    idempotency_key means that event has already been fully processed;
    process_webhook_event() checks this before doing any state mutation."""

    __tablename__ = "webhook_events"

    event_type: Mapped[str] = mapped_column(String(100), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<WebhookEvent(id={self.id}, event_type={self.event_type})>"
