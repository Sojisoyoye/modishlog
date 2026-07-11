"""Shared test fixtures for ModishLog backend tests."""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure a valid SECRET_KEY is present for all tests so that Settings()
# can be instantiated without a .env file in the working directory.
os.environ.setdefault(
    "SECRET_KEY",
    "test-secret-key-that-is-at-least-32-characters-long-for-pytest",
)

# Use a writable temp directory so that src.main's os.makedirs doesn't fail
# when /app/uploads (the Docker path) doesn't exist in the local test env.
os.environ.setdefault("UPLOAD_DIR", "/tmp/modishlog_test_uploads")


@pytest.fixture
def anyio_backend():
    """Use asyncio as the async backend for tests."""
    return "asyncio"


class NestedTransaction:
    """AsyncSession.begin_nested() is a sync method returning an async
    context manager (an AsyncSessionTransaction) — a bare AsyncMock's
    auto-specced children would make `db.begin_nested()` itself return a
    coroutine instead, breaking `async with db.begin_nested():`."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def mock_db():
    """A mocked AsyncSession good enough for service/module-level unit
    tests: db.execute is left for the caller to configure per-test."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.begin_nested = MagicMock(return_value=NestedTransaction())
    return db


# TODO: Add fixtures as domain modules are implemented:
# - db_session: async database session with test database
# - auth_headers: pre-authenticated JWT headers
# - test_user: factory for creating test users
# - test_product: factory for creating test products
