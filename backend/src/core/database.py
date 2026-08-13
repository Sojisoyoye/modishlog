"""Async SQLAlchemy engine and session factory."""

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
    # Explicit pool settings — overridable via DB_POOL_SIZE / DB_MAX_OVERFLOW /
    # DB_POOL_RECYCLE environment variables (see core/config.py).
    # pool_pre_ping=True protects against stale connections dropped by Neon
    # (serverless Postgres) or any TCP-level idle timeout.
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=30,
    pool_recycle=settings.DB_POOL_RECYCLE,
    connect_args={"ssl": True} if settings.DATABASE_SSL else {},
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


class UUIDMixin:
    """Mixin that adds a UUID primary key."""

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Mixin that adds created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class MigrationTaggedMixin:
    """Mixin that tags a row with the data-import migration job that created
    it, so an import's rollback can find and remove exactly its own rows."""

    migration_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("migration_jobs.id"), nullable=True, index=True, default=None
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
