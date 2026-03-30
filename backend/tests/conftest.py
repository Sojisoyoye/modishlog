"""Shared test fixtures for ModishLog backend tests."""

import pytest


@pytest.fixture
def anyio_backend():
    """Use asyncio as the async backend for tests."""
    return "asyncio"


# TODO: Add fixtures as domain modules are implemented:
# - db_session: async database session with test database
# - auth_headers: pre-authenticated JWT headers
# - test_user: factory for creating test users
# - test_product: factory for creating test products
