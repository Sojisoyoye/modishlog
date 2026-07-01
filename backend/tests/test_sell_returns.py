"""Tests for Sell Returns API — TDD before implementation."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.auth.service import build_token
from src.core.security import get_password_hash
import src.suppliers.models  # noqa: F401
from src.sales.models import Sale, SaleChannel, SaleStatus


VALID_PASSWORD = "Str0ng!Pass#99"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(**overrides):
    from src.auth.models import User, UserRole

    defaults = dict(
        email="test@example.com",
        hashed_password=get_password_hash(VALID_PASSWORD),
        full_name="Test User",
        is_active=True,
        role=UserRole.ADMIN,
        failed_login_attempts=0,
        locked_until=None,
    )
    defaults.update(overrides)
    user = User(**defaults)
    user.id = overrides.get("id", uuid.uuid4())
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    return user


def _make_sale(**overrides):
    defaults = dict(
        product_id=uuid.uuid4(),
        quantity=5,
        unit_price=Decimal("150.000000"),
        total_amount=Decimal("750.000000"),
        currency="NGN",
        sale_date=date(2026, 3, 15),
        channel=SaleChannel.RETAIL,
        status=SaleStatus.COMPLETED,
        notes=None,
        recorded_by=uuid.uuid4(),
        transaction_id=None,
    )
    defaults.update(overrides)
    sale = Sale(**defaults)
    sale.id = overrides.get("id", uuid.uuid4())
    sale.created_at = datetime.now(timezone.utc)
    sale.updated_at = datetime.now(timezone.utc)
    return sale


def _make_sell_return(**overrides):
    from src.sales.models import SellReturn

    defaults = dict(
        sale_id=uuid.uuid4(),
        return_date=date(2026, 4, 1),
        total_amount=Decimal("150.000000"),
        amount_paid=Decimal("0"),
        notes=None,
        ref_no=None,
        created_by=uuid.uuid4(),
    )
    defaults.update(overrides)
    sr = SellReturn(**defaults)
    sr.id = overrides.get("id", uuid.uuid4())
    sr.created_at = datetime.now(timezone.utc)
    sr.updated_at = datetime.now(timezone.utc)
    return sr


def _mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock(return_value=None)
    db.delete = AsyncMock()
    return db


def _mock_db_scalar(scalar_result=None):
    db = _mock_db()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = scalar_result
    result_mock.scalar.return_value = scalar_result
    db.execute = AsyncMock(return_value=result_mock)
    return db


def _mock_db_sequence(results: list):
    """Return a db mock whose execute() returns each result in turn."""
    db = _mock_db()
    mocks = []
    for val in results:
        m = MagicMock()
        if isinstance(val, list):
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = val
            m.scalars.return_value = scalars_mock
            m.scalar.return_value = len(val)
            m.scalar_one_or_none.return_value = None
        else:
            m.scalar_one_or_none.return_value = val
            m.scalar.return_value = val
        mocks.append(m)
    db.execute = AsyncMock(side_effect=mocks)
    return db


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


class TestCreateSellReturnService:
    @pytest.mark.asyncio
    async def test_create_sell_return_happy_path(self):
        from src.sales.service import create_sell_return

        sale = _make_sale()
        db = _mock_db_scalar(scalar_result=sale)

        result = await create_sell_return(
            db,
            sale_id=sale.id,
            data=_make_sell_return_create(),
            user_id=uuid.uuid4(),
        )

        db.add.assert_called_once()
        db.flush.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_sell_return_sale_not_found(self):
        from src.sales.exceptions import SaleNotFoundError
        from src.sales.service import create_sell_return

        db = _mock_db_scalar(scalar_result=None)

        with pytest.raises(SaleNotFoundError):
            await create_sell_return(
                db,
                sale_id=uuid.uuid4(),
                data=_make_sell_return_create(),
                user_id=uuid.uuid4(),
            )


class TestListSellReturnsService:
    @pytest.mark.asyncio
    async def test_list_sell_returns_by_sale(self):
        from src.sales.service import list_sell_returns

        sale_id = uuid.uuid4()
        sr1 = _make_sell_return(sale_id=sale_id)
        sr2 = _make_sell_return(sale_id=sale_id)
        db = _mock_db_sequence([2, [sr1, sr2]])

        items, total = await list_sell_returns(db, sale_id=sale_id)

        assert total == 2
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_list_all_sell_returns_paginated(self):
        from src.sales.service import list_sell_returns

        sr1 = _make_sell_return()
        sr2 = _make_sell_return()
        db = _mock_db_sequence([2, [sr1, sr2]])

        items, total = await list_sell_returns(db, page=1, page_size=25)

        assert total == 2
        assert len(items) == 2


class TestGetSellReturnService:
    @pytest.mark.asyncio
    async def test_get_sell_return_happy_path(self):
        from src.sales.service import get_sell_return

        sr = _make_sell_return()
        db = _mock_db_scalar(scalar_result=sr)

        result = await get_sell_return(db, return_id=sr.id)

        assert result.id == sr.id

    @pytest.mark.asyncio
    async def test_get_sell_return_not_found(self):
        from src.sales.exceptions import SellReturnNotFoundError
        from src.sales.service import get_sell_return

        db = _mock_db_scalar(scalar_result=None)

        with pytest.raises(SellReturnNotFoundError):
            await get_sell_return(db, return_id=uuid.uuid4())


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestSellReturnsEndpoints:
    @pytest.fixture(autouse=True)
    def _setup_client(self):
        from src.main import app

        self.app = app
        self._original_overrides = app.dependency_overrides.copy()
        yield
        app.dependency_overrides = self._original_overrides

    def _override_db(self, db_mock):
        from src.core.database import get_db

        async def _fake_db():
            yield db_mock

        self.app.dependency_overrides[get_db] = _fake_db

    def _override_auth(self, user=None):
        from src.auth.dependencies import get_current_active_user

        u = user or _make_user()
        self.app.dependency_overrides[get_current_active_user] = lambda: u
        return u

    def test_create_sell_return_endpoint_created(self):
        user = self._override_auth()
        sale = _make_sale(recorded_by=user.id)
        db = _mock_db_scalar(scalar_result=sale)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.post(
                f"/api/v1/sales/{sale.id}/returns",
                json={
                    "return_date": "2026-04-01",
                    "total_amount": "150.00",
                    "amount_paid": "0",
                    "ref_no": "RET-001",
                    "notes": "Customer return",
                },
            )

        assert resp.status_code == 201

    def test_create_sell_return_sale_not_found(self):
        self._override_auth()
        db = _mock_db_scalar(scalar_result=None)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.post(
                f"/api/v1/sales/{uuid.uuid4()}/returns",
                json={
                    "return_date": "2026-04-01",
                    "total_amount": "150.00",
                },
            )

        assert resp.status_code == 404

    def test_list_sell_returns_by_sale(self):
        user = self._override_auth()
        sale_id = uuid.uuid4()
        sr1 = _make_sell_return(sale_id=sale_id, created_by=user.id)
        sr2 = _make_sell_return(sale_id=sale_id, created_by=user.id)
        db = _mock_db_sequence([2, [sr1, sr2]])
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/sales/{sale_id}/returns")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_list_all_sell_returns(self):
        user = self._override_auth()
        sr1 = _make_sell_return(created_by=user.id)
        sr2 = _make_sell_return(created_by=user.id)
        db = _mock_db_sequence([2, [sr1, sr2]])
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/sales/returns/sells")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    def test_get_sell_return_endpoint(self):
        user = self._override_auth()
        sr = _make_sell_return(created_by=user.id)
        db = _mock_db_scalar(scalar_result=sr)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/sales/returns/sells/{sr.id}")

        assert resp.status_code == 200
        assert resp.json()["id"] == str(sr.id)

    def test_get_sell_return_not_found(self):
        self._override_auth()
        db = _mock_db_scalar(scalar_result=None)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/sales/returns/sells/{uuid.uuid4()}")

        assert resp.status_code == 404

    def test_returns_requires_auth(self):
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/sales/returns/sells")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Helper (defined after fixtures to avoid import errors)
# ---------------------------------------------------------------------------


def _make_sell_return_create():
    from src.sales.schemas import SellReturnCreate

    return SellReturnCreate(
        return_date=date(2026, 4, 1),
        total_amount=Decimal("150.000000"),
        amount_paid=Decimal("0"),
        ref_no="RET-001",
        notes="Customer return",
    )
