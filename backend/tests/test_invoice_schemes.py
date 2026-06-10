"""Tests for invoice numbering schemes."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.invoice_schemes.exceptions import SchemeNotFoundError
from src.invoice_schemes.models import InvoiceScheme, SchemeType
from src.invoice_schemes.schemas import SchemeCreate, SchemeUpdate
from src.invoice_schemes.service import (
    create_scheme,
    generate_preview,
    get_scheme,
    list_schemes,
    update_scheme,
)


def _make_scheme(**overrides):
    """Build a minimal InvoiceScheme for tests."""
    defaults = dict(
        name="Default Scheme",
        scheme_type=SchemeType.BLANK,
        prefix="INV-",
        start_number=1,
        total_digits=5,
        next_number=1,
        is_active=True,
        created_by=uuid.uuid4(),
    )
    defaults.update(overrides)
    scheme = InvoiceScheme(**defaults)
    scheme.id = overrides.get("id", uuid.uuid4())
    scheme.created_at = datetime.now(timezone.utc)
    scheme.updated_at = datetime.now(timezone.utc)
    return scheme


def _mock_db_with_get(entity=None):
    """Return an AsyncMock db where db.get() returns entity."""
    db = AsyncMock()
    db.get = AsyncMock(return_value=entity)
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


def _mock_db_with_execute(scalar_result=None, scalars_result=None):
    """Return an AsyncMock db where db.execute() returns configurable results."""
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = scalar_result
    result_mock.scalar.return_value = scalar_result
    if scalars_result is not None:
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = scalars_result
        result_mock.scalars.return_value = scalars_mock
    db.execute.return_value = result_mock
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock(return_value=None)
    db.delete = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Create scheme tests
# ---------------------------------------------------------------------------


class TestCreateScheme:
    @pytest.mark.asyncio
    async def test_create_scheme_happy_path(self):
        db = _mock_db_with_execute()
        data = SchemeCreate(name="My Scheme", prefix="INV-", total_digits=5)
        user_id = uuid.uuid4()
        scheme = await create_scheme(db, data, user_id)
        assert scheme.name == "My Scheme"
        assert scheme.prefix == "INV-"
        assert scheme.created_by == user_id
        db.add.assert_called_once()
        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_scheme_not_found(self):
        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(SchemeNotFoundError):
            await get_scheme(db, uuid.uuid4())


# ---------------------------------------------------------------------------
# List schemes tests
# ---------------------------------------------------------------------------


class TestListSchemes:
    @pytest.mark.asyncio
    async def test_list_schemes_returns_all(self):
        scheme1 = _make_scheme(name="Scheme A")
        scheme2 = _make_scheme(name="Scheme B")
        db = _mock_db_with_execute(scalars_result=[scheme1, scheme2])
        result = await list_schemes(db)
        assert len(result) == 2
        assert result[0].name == "Scheme A"
        assert result[1].name == "Scheme B"


# ---------------------------------------------------------------------------
# Generate preview tests (pure sync function)
# ---------------------------------------------------------------------------


class TestGeneratePreview:
    def test_generate_preview_blank_type(self):
        scheme = _make_scheme(
            scheme_type=SchemeType.BLANK,
            prefix="INV-",
            next_number=42,
            total_digits=5,
        )
        preview = generate_preview(scheme)
        assert preview == "INV-00042"

    def test_generate_preview_year_type(self):
        from datetime import datetime, timezone

        scheme = _make_scheme(
            scheme_type=SchemeType.YEAR,
            prefix="ORD-",
            next_number=7,
            total_digits=4,
        )
        preview = generate_preview(scheme)
        year = datetime.now(timezone.utc).year
        assert preview == f"ORD-{year}-0007"
