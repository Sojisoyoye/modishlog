"""TDD tests for Expenses domain (task #164) — write FIRST, confirm red."""

import io
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.core.security import get_password_hash

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


def _mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.delete = MagicMock()
    return db


def _make_category(**overrides):
    from src.expenses.models import ExpenseCategory

    defaults = dict(
        name="Office Supplies",
        description="Paper, pens, etc.",
        created_by=uuid.uuid4(),
    )
    defaults.update(overrides)
    cat = ExpenseCategory(**defaults)
    cat.id = overrides.get("id", uuid.uuid4())
    cat.created_at = datetime.now(timezone.utc)
    cat.updated_at = datetime.now(timezone.utc)
    return cat


def _make_expense(**overrides):
    from src.expenses.models import Expense

    defaults = dict(
        category_id=None,
        ref_no="EXP-001",
        amount_ngn=Decimal("50000.000000"),
        fx_rate=Decimal("1500.000000"),
        amount_usd=Decimal("33.333333"),
        currency="USD",
        expense_date=date(2026, 7, 1),
        payment_method="bank_transfer",
        note="Monthly rent",
        location_id=None,
        created_by=uuid.uuid4(),
    )
    defaults.update(overrides)
    exp = Expense(**defaults)
    exp.id = overrides.get("id", uuid.uuid4())
    exp.category = None
    exp.created_at = datetime.now(timezone.utc)
    exp.updated_at = datetime.now(timezone.utc)
    return exp


# ---------------------------------------------------------------------------
# Service-layer unit tests
# ---------------------------------------------------------------------------


class TestExpensesService:
    @pytest.mark.asyncio
    async def test_create_expense_category(self):
        """create_category returns ExpenseCategory with the given name."""
        from src.expenses.schemas import ExpenseCategoryCreate
        from src.expenses.service import create_category

        db = _mock_db()
        data = ExpenseCategoryCreate(name="Travel", description="Business travel")
        user_id = uuid.uuid4()

        cat = await create_category(db, data, user_id)

        db.add.assert_called_once()
        db.flush.assert_called_once()
        assert cat.name == "Travel"
        assert cat.created_by == user_id

    @pytest.mark.asyncio
    async def test_list_categories(self):
        """list_categories returns all ExpenseCategory rows."""
        from src.expenses.service import list_categories

        cat1 = _make_category(name="Food")
        cat2 = _make_category(name="Transport")

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [cat1, cat2]

        db = _mock_db()
        db.execute = AsyncMock(return_value=result_mock)

        cats = await list_categories(db)

        assert len(cats) == 2

    @pytest.mark.asyncio
    async def test_create_expense_with_category(self):
        """create_expense persists expense with category_id set."""
        from src.expenses.schemas import ExpenseCreate
        from src.expenses.service import create_expense

        db = _mock_db()
        cat_id = uuid.uuid4()
        data = ExpenseCreate(
            category_id=cat_id,
            amount_ngn=Decimal("10000"),
            amount_usd=Decimal("6.67"),
            expense_date=date(2026, 7, 1),
        )
        user_id = uuid.uuid4()

        # selectinload triggers a second execute for the relationship
        cat_mock = MagicMock()
        cat_mock.scalar_one_or_none.return_value = None  # reloaded expense
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = _make_expense(category_id=cat_id)
        db.execute = AsyncMock(return_value=result_mock)

        exp = await create_expense(db, data, user_id)

        db.add.assert_called_once()
        assert exp.category_id == cat_id

    @pytest.mark.asyncio
    async def test_create_expense_without_category(self):
        """create_expense accepts category_id=None."""
        from src.expenses.schemas import ExpenseCreate
        from src.expenses.service import create_expense

        db = _mock_db()
        data = ExpenseCreate(
            category_id=None,
            amount_ngn=Decimal("5000"),
            amount_usd=Decimal("3.33"),
            expense_date=date(2026, 7, 1),
        )
        user_id = uuid.uuid4()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = _make_expense(category_id=None)
        db.execute = AsyncMock(return_value=result_mock)

        exp = await create_expense(db, data, user_id)

        assert exp.category_id is None

    @pytest.mark.asyncio
    async def test_list_expenses_filter_by_category(self):
        """list_expenses with category_id filter returns only that category's expenses."""
        from src.expenses.service import list_expenses

        cat_id = uuid.uuid4()
        exp = _make_expense(category_id=cat_id)

        count_mock = MagicMock()
        count_mock.scalar.return_value = 1

        items_mock = MagicMock()
        items_mock.scalars.return_value.all.return_value = [exp]

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[count_mock, items_mock])

        items, total = await list_expenses(db, category_id=cat_id)

        assert total == 1
        assert items[0].category_id == cat_id

    @pytest.mark.asyncio
    async def test_list_expenses_filter_by_date_range(self):
        """list_expenses with date_from/date_to returns (items, total)."""
        from src.expenses.service import list_expenses

        exp = _make_expense(expense_date=date(2026, 6, 15))

        count_mock = MagicMock()
        count_mock.scalar.return_value = 1

        items_mock = MagicMock()
        items_mock.scalars.return_value.all.return_value = [exp]

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[count_mock, items_mock])

        items, total = await list_expenses(
            db,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
        )

        assert total == 1
        assert items[0].expense_date == date(2026, 6, 15)

    @pytest.mark.asyncio
    async def test_update_expense(self):
        """update_expense patches only provided fields."""
        from src.expenses.schemas import ExpenseUpdate
        from src.expenses.service import update_expense

        exp = _make_expense(note="original")

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = exp
        db = _mock_db()
        db.execute = AsyncMock(return_value=result_mock)

        data = ExpenseUpdate(note="updated note")
        updated = await update_expense(db, exp.id, data)

        assert updated.note == "updated note"

    @pytest.mark.asyncio
    async def test_delete_expense(self):
        """delete_expense calls db.delete then db.flush."""
        from src.expenses.service import delete_expense

        exp = _make_expense()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = exp
        db = _mock_db()
        db.execute = AsyncMock(return_value=result_mock)

        await delete_expense(db, exp.id)

        db.delete.assert_called_once_with(exp)
        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_expense_not_found(self):
        """get_expense raises ExpenseNotFoundError for unknown id."""
        from src.expenses.exceptions import ExpenseNotFoundError
        from src.expenses.service import get_expense

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db = _mock_db()
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(ExpenseNotFoundError):
            await get_expense(db, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_export_expenses_csv_returns_valid_csv(self):
        """export_expenses_csv returns a string with a valid CSV header."""
        from src.expenses.service import export_expenses_csv

        exp = _make_expense()

        count_mock = MagicMock()
        count_mock.scalar.return_value = 1

        items_mock = MagicMock()
        items_mock.scalars.return_value.all.return_value = [exp]

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[count_mock, items_mock])

        csv_str = await export_expenses_csv(db)

        assert isinstance(csv_str, str)
        first_line = csv_str.splitlines()[0]
        assert "date" in first_line.lower() or "expense_date" in first_line.lower()


# ---------------------------------------------------------------------------
# Endpoint integration tests
# ---------------------------------------------------------------------------


class TestExpenseEndpoints:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from src.main import app

        self.app = app
        self._orig = app.dependency_overrides.copy()
        yield
        app.dependency_overrides = self._orig

    def _override_db(self, db):
        from src.auth.dependencies import get_current_active_user
        from src.core.database import get_db

        async def _fake_db():
            yield db

        self.app.dependency_overrides[get_db] = _fake_db
        self.app.dependency_overrides[get_current_active_user] = lambda: _make_user()

    def test_list_expenses_endpoint_ok(self):
        """GET /expenses returns 200 with items + total."""
        db = _mock_db()
        exp = _make_expense()

        count_mock = MagicMock()
        count_mock.scalar.return_value = 1

        items_mock = MagicMock()
        items_mock.scalars.return_value.all.return_value = [exp]

        db.execute = AsyncMock(side_effect=[count_mock, items_mock])
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/expenses")

        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert body["total"] == 1

    def test_create_expense_endpoint_ok(self):
        """POST /expenses returns 201 with id in body."""
        db = _mock_db()
        exp = _make_expense()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = exp
        db.execute = AsyncMock(return_value=result_mock)
        self._override_db(db)

        payload = {
            "amount_ngn": "50000.00",
            "amount_usd": "33.33",
            "expense_date": "2026-07-01",
        }

        with TestClient(self.app) as client:
            resp = client.post("/api/v1/expenses", json=payload)

        assert resp.status_code == 201
        assert "id" in resp.json()

    def test_get_expense_endpoint_ok(self):
        """GET /expenses/{id} returns 200 with correct fields."""
        db = _mock_db()
        exp = _make_expense()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = exp
        db.execute = AsyncMock(return_value=result_mock)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/expenses/{exp.id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(exp.id)
        assert "amount_usd" in body

    def test_get_expense_not_found_endpoint(self):
        """GET /expenses/{bad_id} returns 404."""
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/expenses/{uuid.uuid4()}")

        assert resp.status_code == 404

    def test_list_categories_endpoint(self):
        """GET /expense-categories returns 200 with a list."""
        db = _mock_db()
        cat = _make_category()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [cat]
        db.execute = AsyncMock(return_value=result_mock)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/expense-categories")

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert body[0]["name"] == cat.name
