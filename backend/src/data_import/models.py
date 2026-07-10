"""Data import (ETL) domain SQLAlchemy models."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin


class MigrationJobStatus(str, enum.Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    TRANSFORMING = "transforming"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    IMPORTING = "importing"
    RECOMPUTING = "recomputing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


class SourceSystem(str, enum.Enum):
    ULTIMATEPOS = "ultimatepos"
    QUICKBOOKS = "quickbooks"
    SHOPIFY = "shopify"
    GENERIC = "generic"


class ExtractionMode(str, enum.Enum):
    CSV = "csv"
    API = "api"


class MigrationJob(UUIDMixin, TimestampMixin, Base):
    """Tracks a single data-import run for a business."""

    __tablename__ = "migration_jobs"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )
    status: Mapped[MigrationJobStatus] = mapped_column(
        Enum(MigrationJobStatus, values_callable=lambda x: [e.value for e in x]),
        default=MigrationJobStatus.PENDING,
    )
    source_system: Mapped[SourceSystem] = mapped_column(
        Enum(SourceSystem, values_callable=lambda x: [e.value for e in x])
    )
    extraction_mode: Mapped[ExtractionMode] = mapped_column(
        Enum(ExtractionMode, values_callable=lambda x: [e.value for e in x]),
        default=ExtractionMode.CSV,
    )
    # Live-API mode only. Credentials are NEVER stored here or anywhere else —
    # they're passed per-request and discarded once extraction finishes.
    api_base_url: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    checkpoint: Mapped[dict] = mapped_column(JSONB, default=dict)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    row_counts: Mapped[dict] = mapped_column(JSONB, default=dict)
    validation_errors: Mapped[list] = mapped_column(JSONB, default=list)
    validation_warnings: Mapped[list] = mapped_column(JSONB, default=list)
    options: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    def __repr__(self) -> str:
        return f"<MigrationJob(id={self.id}, status={self.status})>"


# Statuses from which the job may legally transition to `importing` — i.e. the
# confirm endpoint is the *only* trigger and only fires from this state.
CONFIRMABLE_STATUSES = {MigrationJobStatus.AWAITING_CONFIRMATION}
