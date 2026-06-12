"""Tests for inventory HTTP endpoints (adjust, movements)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.core.security import get_password_hash
from src.inventory.models import InventoryLevel, MovementType, StockMovement


VALID_PASSWORD = "Str0ng!Pass#99"


# ---------------------------------------------------------------------------
# Object factories
# ---------------------------------------------------------------------------


def _make_user(**overrides):
    from src.auth.models import User, UserRole

    defaults = dict(
        email="inv_test@example.com",
        hashed_password=get_password_hash(VALID_PASSWORD),
        full_name="Inv Test User",
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


def _make_inventory(product_id=None, **overrides):
    defaults = dict(
        product_id=product_id or uuid.uuid4(),
        quantity_on_hand=100,
        quantity_reserved=0,
        low_stock_threshold=10,
        last_replenished_at=None,
    )
    defaults.update(overrides)
    inv = InventoryLevel(**defaults)
    inv.id = overrides.get("id", uuid.uuid4())
    inv.created_at = datetime.now(timezone.utc)
    inv.updated_at = datetime.now(timezone.utc)
    return inv


def _make_movement(product_id=None, movement_type=MovementType.MANUAL_ADD, quantity_change=10):
    mov = StockMovement(
        product_id=product_id or uuid.uuid4(),
        movement_type=movement_type,
        quantity_change=quantity_change,
        quantity_before=100,
        quantity_after=110,
        reason="test reason",
        performed_by=uuid.uuid4(),
    )
    mov.id = uuid.uuid4()
    mov.created_at = datetime.now(timezone.utc)
    return mov


def _mock_db(inventory=None, movements=None, user=None):
    """Build a mock AsyncSession that handles auth (db.get) and inventory queries (db.execute)."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock(return_value=user)  # used by auth dependency

    result_mock = MagicMock()
    # For get_inventory_level (scalar_one_or_none)
    result_mock.scalar_one_or_none.return_value = inventory
    result_mock.scalar.return_value = inventory
    # For list_stock_movements / list all movements (scalars().all())
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = movements or []
    result_mock.scalars.return_value = scalars_mock

    db.execute.return_value = result_mock
    return db


# ---------------------------------------------------------------------------
# Endpoint test helpers
# ---------------------------------------------------------------------------


class _InventoryEndpointBase:
    @pytest.fixture(autouse=True)
    def setup(self):
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

    def _auth_headers(self, user=None):
        from src.auth.service import build_token

        u = user or _make_user()
        token = build_token(u)
        return {"Authorization": f"Bearer {token}"}, u

    def _override_auth(self):
        from src.auth.dependencies import get_current_active_user
        u = _make_user()
        async def _fake_auth():
            return u
        self.app.dependency_overrides[get_current_active_user] = _fake_auth


# ---------------------------------------------------------------------------
# POST /inventory/{product_id}/adjust
# ---------------------------------------------------------------------------


class TestInventoryAdjustEndpoint(_InventoryEndpointBase):
    def test_adjust_stock_success(self):
        """Authenticated POST /adjust with valid payload returns 200 and updated stock."""
        user = _make_user()
        inv = _make_inventory(quantity_on_hand=50)
        db = _mock_db(inventory=inv, user=user)
        self._override_db(db)
        headers, _ = self._auth_headers(user)

        with TestClient(self.app) as client:
            resp = client.post(
                f"/api/v1/inventory/{inv.product_id}/adjust",
                json={
                    "quantity_change": 10,
                    "movement_type": "manual_add",
                    "reason": "Restocking shelves",
                },
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        # quantity_on_hand updated in-memory by adjust_stock service
        assert data["quantity_on_hand"] == 60  # 50 + 10
        assert data["product_id"] == str(inv.product_id)
        db.flush.assert_called_once()
        db.add.assert_called_once()  # StockMovement recorded

    def test_adjust_stock_product_not_found(self):
        """POST /adjust when no inventory record exists → 404."""
        user = _make_user()
        db = _mock_db(inventory=None, user=user)  # no inventory level
        self._override_db(db)
        headers, _ = self._auth_headers(user)

        with TestClient(self.app) as client:
            resp = client.post(
                f"/api/v1/inventory/{uuid.uuid4()}/adjust",
                json={"quantity_change": 5, "movement_type": "manual_add", "reason": "Test"},
                headers=headers,
            )

        assert resp.status_code == 404

    def test_adjust_stock_would_go_negative(self):
        """POST /adjust when removal would make stock negative → 400."""
        user = _make_user()
        inv = _make_inventory(quantity_on_hand=5)
        db = _mock_db(inventory=inv, user=user)
        self._override_db(db)
        headers, _ = self._auth_headers(user)

        with TestClient(self.app) as client:
            resp = client.post(
                f"/api/v1/inventory/{inv.product_id}/adjust",
                json={
                    "quantity_change": -10,
                    "movement_type": "manual_remove",
                    "reason": "Remove more than available",
                },
                headers=headers,
            )

        assert resp.status_code == 400

    def test_adjust_stock_invalid_movement_type(self):
        """POST /adjust with unknown movement_type → 422 validation error."""
        user = _make_user()
        inv = _make_inventory()
        db = _mock_db(inventory=inv, user=user)
        self._override_db(db)
        headers, _ = self._auth_headers(user)

        with TestClient(self.app) as client:
            resp = client.post(
                f"/api/v1/inventory/{inv.product_id}/adjust",
                json={"quantity_change": 5, "movement_type": "unknown_type", "reason": "Test"},
                headers=headers,
            )

        assert resp.status_code == 422

    def test_adjust_stock_empty_reason_rejected(self):
        """POST /adjust with empty reason string → 422 validation error."""
        user = _make_user()
        inv = _make_inventory()
        db = _mock_db(inventory=inv, user=user)
        self._override_db(db)
        headers, _ = self._auth_headers(user)

        with TestClient(self.app) as client:
            resp = client.post(
                f"/api/v1/inventory/{inv.product_id}/adjust",
                json={"quantity_change": 5, "movement_type": "manual_add", "reason": ""},
                headers=headers,
            )

        assert resp.status_code == 422

    def test_adjust_stock_requires_auth(self):
        """POST /adjust without auth → 401."""
        db = _mock_db()
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.post(
                f"/api/v1/inventory/{uuid.uuid4()}/adjust",
                json={"quantity_change": 10, "movement_type": "manual_add", "reason": "test"},
            )

        assert resp.status_code == 401

    def test_adjust_stock_uses_select_for_update(self):
        """adjust_stock must issue SELECT ... FOR UPDATE to prevent concurrent oversell."""
        import asyncio
        from src.inventory import service as inv_service

        user = _make_user()
        inv = _make_inventory(quantity_on_hand=5)
        db = _mock_db(inventory=inv, user=user)

        asyncio.run(
            inv_service.adjust_stock(db, inv.product_id, -1, "sale_depletion", "Test sale", user.id)
        )

        # First db.execute call must be the locked SELECT — inspect the query object
        first_call = db.execute.call_args_list[0]
        query = first_call[0][0]
        # with_for_update() sets _for_update_arg on the Select object
        assert getattr(query, "_for_update_arg", None) is not None, (
            "adjust_stock must use .with_for_update() on the InventoryLevel SELECT "
            "to prevent concurrent oversell race conditions"
        )


# ---------------------------------------------------------------------------
# GET /inventory/movements  (new endpoint — all recent movements)
# ---------------------------------------------------------------------------


class TestListMovementsEndpoint(_InventoryEndpointBase):
    def test_list_all_movements_returns_200(self):
        """GET /inventory/movements returns list of recent movements."""
        self._override_auth()
        mov1 = _make_movement(quantity_change=10)
        mov2 = _make_movement(movement_type=MovementType.SALE_DEPLETION, quantity_change=-2)
        db = _mock_db(movements=[mov1, mov2])
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/inventory/movements")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        # quantity_change field must be present (not the old 'quantity' alias)
        assert "quantity_change" in data[0]
        assert data[0]["quantity_change"] == 10

    def test_list_all_movements_empty(self):
        """GET /inventory/movements with no data → empty list."""
        self._override_auth()
        db = _mock_db(movements=[])
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/inventory/movements")

        assert resp.status_code == 200
        assert resp.json() == []
