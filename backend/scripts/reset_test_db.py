#!/usr/bin/env python3
"""
Reset the E2E test database to a clean state with minimal fixtures.

Called by Playwright globalSetup before each test suite run:
  1. Runs Alembic migrations to head (creates schema on fresh tmpfs DB)
  2. Wipes all rows via ORM delete() in FK-safe order
  3. Seeds the single E2E test user

Usage (inside docker compose exec backend):
  DATABASE_URL=postgresql+asyncpg://modishlog:modishlog_dev@db_test/modishlog_test \
    python scripts/reset_test_db.py
"""

import asyncio
import logging
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import structlog
from alembic import command
from alembic.config import Config
from passlib.context import CryptContext
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pos_migrate import WIPE_ORDER
from src.auth.models import Business, User, UserRole

log = structlog.get_logger()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://modishlog:modishlog_dev@db_test/modishlog_test",
)

E2E_USER_EMAIL = "e2e-suite@modishlogtest.com"
E2E_USER_PASSWORD = "E2eTest!1234"

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

_ALEMBIC_INI = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")


def _run_migrations() -> None:
    """Apply all Alembic migrations to head on the test DB."""
    cfg = Config(_ALEMBIC_INI)
    # Override the URL so Alembic targets the test DB, not whatever is in alembic.ini
    sync_url = DATABASE_URL.replace("+asyncpg", "")
    cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(cfg, "head")
    log.info("alembic_migrations_applied", db=DATABASE_URL)


async def _wipe_and_seed() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        for model in WIPE_ORDER:
            await session.execute(delete(model))
        # Business is not in WIPE_ORDER (no FK dependents there), delete separately.
        await session.execute(delete(Business))
        log.info("test_db_wiped")

        business = Business(
            id=uuid.uuid4(),
            name="E2E Test Business",
            currency="NGN",
        )
        session.add(business)
        await session.flush()

        user = User(
            id=uuid.uuid4(),
            email=E2E_USER_EMAIL,
            full_name="E2E Tester",
            hashed_password=pwd_ctx.hash(E2E_USER_PASSWORD),
            is_active=True,
            role=UserRole.ADMIN,
            business_id=business.id,
        )
        session.add(user)
        await session.commit()

    await engine.dispose()
    log.info("test_db_reset_complete", user=E2E_USER_EMAIL)


def _configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%H:%M:%S"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
    )


if __name__ == "__main__":
    # _run_migrations calls alembic which internally calls asyncio.run().
    # It must run OUTSIDE any asyncio.run() call to avoid "cannot be called
    # from a running event loop" errors.
    _configure_logging()
    _run_migrations()
    asyncio.run(_wipe_and_seed())
