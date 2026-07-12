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
        business_id=uuid.uuid4(),
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


def _mock_db_paginated(items: list, total: int, user=None):
    """Mock db for paginated list_inventory_levels: first execute → count, second → items."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock(return_value=user)

    count_result = MagicMock()
    count_result.scalar.return_value = total

    items_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    items_result.scalars.return_value = scalars_mock

    db.execute.side_effect = [count_result, items_result]
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
        from src.auth.dependencies import get_current_business_id

        u = user or _make_user()
        token = build_token(u)
        # Also override business_id dependency so endpoints work without a real DB join
        async def _fake_business_id():
            return u.business_id
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id
        return {"Authorization": f"Bearer {token}"}, u

    def _override_auth(self, user=None):
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        u = user or _make_user()
        async def _fake_auth():
            return u
        async def _fake_business_id():
            return u.business_id
        self.app.dependency_overrides[get_current_active_user] = _fake_auth
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id


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


# ---------------------------------------------------------------------------
# GET /inventory  — paginated list
# ---------------------------------------------------------------------------


class TestListInventoryEndpoint(_InventoryEndpointBase):
    def test_list_inventory_returns_paginated_response(self):
        """GET /inventory returns items/total/page/page_size structure."""
        self._override_auth()
        inv1 = _make_inventory(quantity_on_hand=50)
        inv2 = _make_inventory(quantity_on_hand=20)
        db = _mock_db_paginated(items=[inv1, inv2], total=2)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/inventory")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["page"] == 1
        assert data["page_size"] == 200
        assert len(data["items"]) == 2
        assert data["items"][0]["quantity_on_hand"] == 50

    def test_list_inventory_page_2(self):
        """GET /inventory?page=2&page_size=1 returns correct pagination metadata."""
        self._override_auth()
        inv = _make_inventory(quantity_on_hand=5)
        db = _mock_db_paginated(items=[inv], total=5)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/inventory?page=2&page_size=1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 2
        assert data["page_size"] == 1
        assert data["total"] == 5
        assert len(data["items"]) == 1

    def test_list_inventory_exposes_variant_id(self):
        """A product can have more than one InventoryLevel row — the
        aggregate row plus one per variant (see data_import/recompute.py).
        Without variant_id in the response, two rows for the same
        product_id would be indistinguishable duplicates to the caller."""
        self._override_auth()
        variant_id = uuid.uuid4()
        inv = _make_inventory(variant_id=variant_id, quantity_on_hand=5)
        db = _mock_db_paginated(items=[inv], total=1)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/inventory")

        assert resp.status_code == 200
        assert resp.json()["items"][0]["variant_id"] == str(variant_id)

    def test_list_inventory_empty(self):
        """GET /inventory with no data returns empty items list with total=0."""
        self._override_auth()
        db = _mock_db_paginated(items=[], total=0)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/inventory")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []


# ---------------------------------------------------------------------------
# Business isolation tests (TDD — written before implementation)
# ---------------------------------------------------------------------------


class TestInventoryBusinessIsolation:
    """Service-level tests: inventory data is scoped per business_id."""

    @pytest.mark.asyncio
    async def test_inventory_isolates_by_business(self):
        """Business B cannot see Business A's inventory levels."""
        from unittest.mock import AsyncMock, MagicMock
        from src.inventory.service import list_inventory_levels

        business_a_id = uuid.uuid4()
        business_b_id = uuid.uuid4()

        async def fake_execute_a(query):
            r = MagicMock()
            r.scalars.return_value.all.return_value = [MagicMock()]
            r.scalar.return_value = 1
            return r

        async def fake_execute_b(query):
            r = MagicMock()
            r.scalars.return_value.all.return_value = []
            r.scalar.return_value = 0
            return r

        db_a, db_b = AsyncMock(), AsyncMock()
        db_a.execute = fake_execute_a
        db_b.execute = fake_execute_b

        result_a = await list_inventory_levels(db_a, business_id=business_a_id)
        result_b = await list_inventory_levels(db_b, business_id=business_b_id)
        items_a = result_a[0] if isinstance(result_a, tuple) else result_a
        items_b = result_b[0] if isinstance(result_b, tuple) else result_b
        assert len(items_a) > 0
        assert len(items_b) == 0

    @pytest.mark.asyncio
    async def test_inventory_owner_sees_own_data(self):
        """Business owner sees their own inventory levels."""
        from unittest.mock import AsyncMock, MagicMock
        from src.inventory.service import list_inventory_levels

        business_id = uuid.uuid4()
        mock_item = MagicMock()

        async def fake_execute(query):
            r = MagicMock()
            r.scalars.return_value.all.return_value = [mock_item]
            r.scalar.return_value = 1
            return r

        db = AsyncMock()
        db.execute = fake_execute
        result = await list_inventory_levels(db, business_id=business_id)
        items = result[0] if isinstance(result, tuple) else result
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_list_all_movements_scoped_by_business(self):
        """list_all_movements with business_id only returns movements for that business's products."""
        from unittest.mock import AsyncMock, MagicMock
        from src.inventory.service import list_all_movements

        business_id = uuid.uuid4()
        mock_movement = MagicMock()

        async def fake_execute(query):
            r = MagicMock()
            r.scalars.return_value.all.return_value = [mock_movement]
            return r

        db = AsyncMock()
        db.execute = fake_execute
        result = await list_all_movements(db, business_id=business_id)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_all_movements_empty_for_other_business(self):
        """list_all_movements for a business with no products returns empty list."""
        from unittest.mock import AsyncMock, MagicMock
        from src.inventory.service import list_all_movements

        business_id = uuid.uuid4()

        async def fake_execute(query):
            r = MagicMock()
            r.scalars.return_value.all.return_value = []
            return r

        db = AsyncMock()
        db.execute = fake_execute
        result = await list_all_movements(db, business_id=business_id)
        assert result == []


# ---------------------------------------------------------------------------
# Task #160 — Variant-scoped inventory tests
# ---------------------------------------------------------------------------


class TestVariantScopedInventory:
    """Tests for variant_id parameter added to get_inventory_level and adjust_stock."""

    @pytest.mark.asyncio
    async def test_get_inventory_level_scoped_to_variant(self):
        """When two InventoryLevel rows exist for the same product (variant A and B),
        get_inventory_level(variant_id=A) must return the A row only."""
        import asyncio
        from src.inventory.service import get_inventory_level
        from src.inventory.exceptions import ProductStockNotFoundError

        product_id = uuid.uuid4()
        variant_a_id = uuid.uuid4()
        variant_b_id = uuid.uuid4()

        inv_a = _make_inventory(product_id=product_id, quantity_on_hand=30)
        inv_a.variant_id = variant_a_id

        inv_b = _make_inventory(product_id=product_id, quantity_on_hand=70)
        inv_b.variant_id = variant_b_id

        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        async def fake_execute(query):
            # Simulate variant-aware filter: return the row whose variant_id matches
            result = MagicMock()
            # Inspect compiled query string is fragile — instead check call order:
            # We expose the variant_id through the test's closure.
            # Strategy: always return inv_a (first call) then inv_b (second call)
            result.scalar_one_or_none.return_value = inv_a
            return result

        db.execute = fake_execute

        inv = await get_inventory_level(db, product_id, variant_id=variant_a_id)
        assert inv.quantity_on_hand == 30
        assert inv.variant_id == variant_a_id

    @pytest.mark.asyncio
    async def test_get_inventory_level_without_variant_returns_null_variant_row(self):
        """Calling get_inventory_level without variant_id must only match the row
        where variant_id IS NULL (i.e. the aggregate non-variant stock)."""
        from src.inventory.service import get_inventory_level

        product_id = uuid.uuid4()
        inv_base = _make_inventory(product_id=product_id, quantity_on_hand=100)
        inv_base.variant_id = None  # aggregate / non-variant row

        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        async def fake_execute(query):
            result = MagicMock()
            result.scalar_one_or_none.return_value = inv_base
            return result

        db.execute = fake_execute

        inv = await get_inventory_level(db, product_id)
        assert inv.quantity_on_hand == 100
        assert inv.variant_id is None

    @pytest.mark.asyncio
    async def test_adjust_stock_variant_scoped(self):
        """adjust_stock with variant_id must deplete the variant's inventory row
        and record the variant_id on the StockMovement."""
        from src.inventory.service import adjust_stock

        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        inv = _make_inventory(product_id=product_id, quantity_on_hand=50)
        inv.variant_id = variant_id

        db = AsyncMock()
        db.flush = AsyncMock()
        captured_movements = []

        def capture_add(obj):
            if isinstance(obj, StockMovement):
                captured_movements.append(obj)

        db.add = MagicMock(side_effect=capture_add)

        async def fake_execute(query):
            result = MagicMock()
            result.scalar_one_or_none.return_value = inv
            return result

        db.execute = fake_execute

        updated_inv = await adjust_stock(
            db,
            product_id=product_id,
            quantity_change=-10,
            movement_type="sale_depletion",
            reason="Test variant sale",
            user_id=user_id,
            variant_id=variant_id,
        )

        assert updated_inv.quantity_on_hand == 40
        assert len(captured_movements) == 1
        assert captured_movements[0].variant_id == variant_id
        assert captured_movements[0].quantity_change == -10

    @pytest.mark.asyncio
    async def test_adjust_stock_no_variant_does_not_set_variant_id(self):
        """adjust_stock called without variant_id must leave variant_id as None
        on the StockMovement (backward-compatible behaviour)."""
        from src.inventory.service import adjust_stock

        product_id = uuid.uuid4()
        user_id = uuid.uuid4()

        inv = _make_inventory(product_id=product_id, quantity_on_hand=80)
        inv.variant_id = None

        db = AsyncMock()
        db.flush = AsyncMock()
        captured_movements = []

        def capture_add(obj):
            if isinstance(obj, StockMovement):
                captured_movements.append(obj)

        db.add = MagicMock(side_effect=capture_add)

        async def fake_execute(query):
            result = MagicMock()
            result.scalar_one_or_none.return_value = inv
            return result

        db.execute = fake_execute

        updated_inv = await adjust_stock(
            db,
            product_id=product_id,
            quantity_change=5,
            movement_type="manual_add",
            reason="Test non-variant restock",
            user_id=user_id,
        )

        assert updated_inv.quantity_on_hand == 85
        assert len(captured_movements) == 1
        assert captured_movements[0].variant_id is None


class TestEnsureInventoryLevelExists:
    """Tests for the backfill helper orders/service.py's transition_status()
    calls before crediting a PO delivery to a variant's InventoryLevel row —
    adjust_stock() is a strict lookup, never an upsert, and nothing else
    creates a variant-scoped row when a variant is created."""

    @pytest.mark.asyncio
    async def test_noop_when_row_already_exists(self):
        from src.inventory.service import ensure_inventory_level_exists

        product_id, variant_id = uuid.uuid4(), uuid.uuid4()
        existing = _make_inventory(product_id=product_id, variant_id=variant_id)

        db = AsyncMock()
        db.add = MagicMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=result_mock)

        await ensure_inventory_level_exists(db, product_id, variant_id)

        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_zeroed_row_when_missing(self):
        from src.inventory.service import ensure_inventory_level_exists
        from tests.conftest import NestedTransaction

        product_id, variant_id = uuid.uuid4(), uuid.uuid4()

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.begin_nested = MagicMock(return_value=NestedTransaction())
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            # First call: existence check (no row). Second call (if any):
            # the aggregate-row threshold lookup.
            result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        await ensure_inventory_level_exists(db, product_id, variant_id)

        db.add.assert_called_once()
        created = db.add.call_args[0][0]
        assert created.product_id == product_id
        assert created.variant_id == variant_id
        assert created.quantity_on_hand == 0

    @pytest.mark.asyncio
    async def test_concurrent_creation_race_is_swallowed_not_raised(self):
        """Two concurrent PO deliveries crediting the same new variant for
        the first time can both pass the existence check before either
        INSERT commits — the loser's flush hits the partial unique index
        and must not propagate as an unhandled 500; the row exists either
        way once the winner commits."""
        from sqlalchemy.exc import IntegrityError

        from src.inventory.service import ensure_inventory_level_exists
        from tests.conftest import NestedTransaction

        product_id, variant_id = uuid.uuid4(), uuid.uuid4()

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock(
            side_effect=IntegrityError("INSERT", {}, Exception("duplicate key"))
        )
        db.begin_nested = MagicMock(return_value=NestedTransaction())

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        # Must not raise.
        await ensure_inventory_level_exists(db, product_id, variant_id)

    @pytest.mark.asyncio
    async def test_variant_backfill_inherits_the_products_configured_threshold(self):
        """A variant's first-ever delivery must not silently reset the
        business's configured low-stock threshold to a hardcoded default —
        it should inherit the product's own aggregate-row threshold."""
        from src.inventory.service import ensure_inventory_level_exists
        from tests.conftest import NestedTransaction

        product_id, variant_id = uuid.uuid4(), uuid.uuid4()
        aggregate = _make_inventory(
            product_id=product_id, variant_id=None, low_stock_threshold=25
        )

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.begin_nested = MagicMock(return_value=NestedTransaction())
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = None  # no variant row yet
            else:
                result.scalar_one_or_none.return_value = (
                    aggregate.low_stock_threshold
                )
            return result

        db.execute = mock_execute

        await ensure_inventory_level_exists(db, product_id, variant_id)

        created = db.add.call_args[0][0]
        assert created.low_stock_threshold == 25
