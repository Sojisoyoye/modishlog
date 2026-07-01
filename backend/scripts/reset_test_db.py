#!/usr/bin/env python3
"""
Reset the E2E test database to a clean state with minimal fixtures.

Called by Playwright globalSetup before each test suite run.
Runs migrations fresh then seeds a single test user.

Usage (inside docker compose exec backend):
  ENVIRONMENT=test DATABASE_URL=... python scripts/reset_test_db.py
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import structlog
from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.auth.models import User, UserRole

log = structlog.get_logger()

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://modishlog:modishlog_dev@db_test/modishlog_test",
)

E2E_USER_EMAIL = "e2e-suite@modishlogtest.com"
E2E_USER_PASSWORD = "E2eTest!1234"

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def reset() -> None:
    import logging

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%H:%M:%S"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
    )

    engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        # Wipe all data using CASCADE on each table to avoid FK ordering
        await conn.execute(text("SET session_replication_role = replica"))
        await conn.execute(text(
            "DO $$ DECLARE r RECORD; BEGIN "
            "FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename != 'alembic_version' "
            "LOOP EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' CASCADE'; "
            "END LOOP; END $$;"
        ))
        await conn.execute(text("SET session_replication_role = DEFAULT"))

    async with factory() as session:
        user = User(
            id=uuid.uuid4(),
            email=E2E_USER_EMAIL,
            full_name="E2E Tester",
            hashed_password=pwd_ctx.hash(E2E_USER_PASSWORD),
            is_active=True,
            role=UserRole.ADMIN,
        )
        session.add(user)
        await session.commit()

    await engine.dispose()
    log.info("test_db_reset_complete", user=E2E_USER_EMAIL)
    print(f"✅ Test DB reset — E2E user: {E2E_USER_EMAIL}")


if __name__ == "__main__":
    asyncio.run(reset())
