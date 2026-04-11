"""Tests for products and inventory CRUD operations."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.auth.service import build_token
from src.core.security import get_password_hash
from src.inventory.exceptions import (
    InvalidStockAdjustmentError,
    ProductStockNotFoundError,
)
from src.inventory.models import InventoryLevel
from src.inventory.service import (
    adjust_stock,
    get_inventory_level,
    initialize_inventory,
)
from src.products.exceptions import (
    CategoryNotFoundError,
    DuplicateSKUError,
    ProductNotFoundError,
)
from src.products.models import Product, ProductCategory
from src.products.schemas import CategoryCreate, ProductCreate, ProductUpdate
from src.products.service import (
    create_category,
    create_product,
    deactivate_product,
    get_product,
    update_product,
)

VALID_PASSWORD = "Str0ng!Pass#99"


def _make_user(**overrides):
    """Build a minimal User for tests."""
    from src.auth.models import User

    defaults = dict(
        email="test@example.com",
        hashed_password=get_password_hash(VALID_PASSWORD),
        full_name="Test User",
        is_active=True,
        failed_login_attempts=0,
        locked_until=None,
    )
    defaults.update(overrides)
    user = User(**defaults)
    user.id = overrides.get("id", uuid.uuid4())
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    return user


def _make_category(**overrides):
    defaults = dict(name="Electronics", description="Electronic goods")
    defaults.update(overrides)
    cat = ProductCategory(**defaults)
    cat.id = overrides.get("id", uuid.uuid4())
    cat.created_at = datetime.now(timezone.utc)
    cat.updated_at = datetime.now(timezone.utc)
    return cat


def _make_product(category_id=None, **overrides):
    defaults = dict(
        name="Test Product",
        sku="PRD-00001",
        description="A test product",
        category_id=category_id or uuid.uuid4(),
        unit_cost=Decimal("100.000000"),
        selling_price=Decimal("150.000000"),
        currency="NGN",
        is_active=True,
    )
    defaults.update(overrides)
    product = Product(**defaults)
    product.id = overrides.get("id", uuid.uuid4())
    product.created_at = datetime.now(timezone.utc)
    product.updated_at = datetime.now(timezone.utc)
    return product


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
# Category tests
# ---------------------------------------------------------------------------


class TestCategoryCRUD:
    @pytest.mark.asyncio
    async def test_create_category(self):
        db = _mock_db_with_execute()
        data = CategoryCreate(name="Electronics", description="Gadgets")
        cat = await create_category(db, data)
        assert cat.name == "Electronics"
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_category_not_found(self):
        db = _mock_db_with_get(entity=None)
        with pytest.raises(CategoryNotFoundError):
            from src.products.service import get_category
            await get_category(db, uuid.uuid4())


# ---------------------------------------------------------------------------
# Product tests
# ---------------------------------------------------------------------------


class TestProductCRUD:
    @pytest.mark.asyncio
    async def test_create_product_without_category(self):
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        db.flush = AsyncMock()
        db.add = MagicMock()

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar.return_value = 0
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = ProductCreate(
            name="No Category Widget",
            unit_cost=Decimal("10"),
            selling_price=Decimal("20"),
        )
        product = await create_product(db, data, uuid.uuid4())
        assert product.name == "No Category Widget"
        assert product.category_id is None
        assert product.sku.startswith("PRD-")

    @pytest.mark.asyncio
    async def test_create_product_auto_sku(self):
        cat = _make_category()
        db = AsyncMock()
        # get_category call (db.get returns the category)
        db.get = AsyncMock(return_value=cat)
        db.flush = AsyncMock()
        db.add = MagicMock()

        # For execute calls: first for SKU count, then for SKU uniqueness check
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # SKU count query
                result.scalar.return_value = 0
            else:
                # SKU uniqueness check
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = ProductCreate(
            name="Widget",
            category_id=cat.id,
            unit_cost=Decimal("10"),
            selling_price=Decimal("20"),
        )
        product = await create_product(db, data, uuid.uuid4())
        assert product.name == "Widget"
        assert product.sku.startswith("PRD-")

    @pytest.mark.asyncio
    async def test_create_product_duplicate_sku(self):
        cat = _make_category()
        existing = _make_product(category_id=cat.id, sku="DUP-SKU")

        db = AsyncMock()
        db.get = AsyncMock(return_value=cat)
        db.flush = AsyncMock()
        db.add = MagicMock()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=result_mock)

        data = ProductCreate(
            name="Widget",
            sku="DUP-SKU",
            category_id=cat.id,
            unit_cost=Decimal("10"),
            selling_price=Decimal("20"),
        )
        with pytest.raises(DuplicateSKUError):
            await create_product(db, data, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_product_not_found(self):
        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(ProductNotFoundError):
            await get_product(db, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_deactivate_product(self):
        product = _make_product()
        db = _mock_db_with_execute(scalar_result=product)
        result = await deactivate_product(db, product.id)
        assert result.is_active is False

    @pytest.mark.asyncio
    async def test_update_product_price_change_creates_history(self):
        product = _make_product(
            unit_cost=Decimal("100"),
            selling_price=Decimal("150"),
        )
        db = _mock_db_with_execute(scalar_result=product)
        # Also need db.get for get_category if category_id not in update
        db.get = AsyncMock(return_value=_make_category())

        data = ProductUpdate(selling_price=Decimal("200"))
        updated = await update_product(db, product.id, data, uuid.uuid4())
        assert updated.selling_price == Decimal("200")
        # PriceHistory should have been added
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_product_no_price_change_no_history(self):
        product = _make_product()
        db = _mock_db_with_execute(scalar_result=product)
        db.get = AsyncMock(return_value=_make_category())

        data = ProductUpdate(name="New Name")
        updated = await update_product(db, product.id, data, uuid.uuid4())
        assert updated.name == "New Name"
        # No PriceHistory should be added
        db.add.assert_not_called()


# ---------------------------------------------------------------------------
# Inventory tests
# ---------------------------------------------------------------------------


class TestInventoryService:
    @pytest.mark.asyncio
    async def test_initialize_inventory(self):
        db = _mock_db_with_execute()
        product_id = uuid.uuid4()
        user_id = uuid.uuid4()
        inv = await initialize_inventory(db, product_id, user_id, initial_stock=50)
        assert inv.product_id == product_id
        assert inv.quantity_on_hand == 50
        # Should have added inventory + movement
        assert db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_initialize_inventory_zero_stock_no_movement(self):
        db = _mock_db_with_execute()
        inv = await initialize_inventory(db, uuid.uuid4(), uuid.uuid4(), initial_stock=0)
        assert inv.quantity_on_hand == 0
        # Only inventory record, no movement
        assert db.add.call_count == 1

    @pytest.mark.asyncio
    async def test_get_inventory_not_found(self):
        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(ProductStockNotFoundError):
            await get_inventory_level(db, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_adjust_stock_add(self):
        inv = _make_inventory(quantity_on_hand=100)
        db = _mock_db_with_execute(scalar_result=inv)
        result = await adjust_stock(
            db,
            product_id=inv.product_id,
            quantity_change=50,
            movement_type="manual_add",
            reason="Restock",
            user_id=uuid.uuid4(),
        )
        assert result.quantity_on_hand == 150

    @pytest.mark.asyncio
    async def test_adjust_stock_remove(self):
        inv = _make_inventory(quantity_on_hand=100)
        db = _mock_db_with_execute(scalar_result=inv)
        result = await adjust_stock(
            db,
            product_id=inv.product_id,
            quantity_change=-30,
            movement_type="manual_remove",
            reason="Damaged",
            user_id=uuid.uuid4(),
        )
        assert result.quantity_on_hand == 70

    @pytest.mark.asyncio
    async def test_adjust_stock_negative_raises(self):
        inv = _make_inventory(quantity_on_hand=10)
        db = _mock_db_with_execute(scalar_result=inv)
        with pytest.raises(InvalidStockAdjustmentError):
            await adjust_stock(
                db,
                product_id=inv.product_id,
                quantity_change=-20,
                movement_type="manual_remove",
                reason="Over-remove",
                user_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_adjust_stock_sets_replenished_at(self):
        inv = _make_inventory(quantity_on_hand=10, last_replenished_at=None)
        db = _mock_db_with_execute(scalar_result=inv)
        await adjust_stock(
            db,
            product_id=inv.product_id,
            quantity_change=50,
            movement_type="order_received",
            reason="Order received",
            user_id=uuid.uuid4(),
        )
        assert inv.last_replenished_at is not None


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestProductEndpoints:
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

    def _auth_headers(self):
        user = _make_user()
        token = build_token(user)
        return {"Authorization": f"Bearer {token}"}, user

    def test_list_categories_empty(self):
        db = _mock_db_with_execute(scalars_result=[])
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/products/categories")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_category_requires_auth(self):
        db = _mock_db_with_execute()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/products/categories",
                json={"name": "Test", "description": "desc"},
            )
        assert resp.status_code == 401

    def test_create_category_success(self):
        db = _mock_db_with_execute()
        # Mock db.get for get_current_user
        user = _make_user()
        db.get = AsyncMock(return_value=user)

        # Simulate flush populating id
        original_add = db.add

        def _add_and_patch(entity):
            if not getattr(entity, "id", None):
                entity.id = uuid.uuid4()
            if not getattr(entity, "created_at", None):
                entity.created_at = datetime.now(timezone.utc)
            if not getattr(entity, "updated_at", None):
                entity.updated_at = datetime.now(timezone.utc)
            return original_add(entity)

        db.add = _add_and_patch
        self._override_db(db)
        headers, _ = self._auth_headers()
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/products/categories",
                json={"name": "Test Category"},
                headers=headers,
            )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Test Category"

    def test_get_product_not_found(self):
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/products/{fake_id}")
        assert resp.status_code == 404

    def test_low_stock_endpoint(self):
        db = _mock_db_with_execute(scalars_result=[])
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/inventory/low-stock")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_upload_product_image_requires_auth(self):
        db = _mock_db_with_execute()
        self._override_db(db)
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.post(
                f"/api/v1/products/{fake_id}/image",
                files={"file": ("test.jpg", b"fake-image-data", "image/jpeg")},
            )
        assert resp.status_code == 401

    def test_upload_product_image_invalid_extension(self):
        db = _mock_db_with_execute()
        user = _make_user()
        db.get = AsyncMock(return_value=user)
        self._override_db(db)
        headers, _ = self._auth_headers()
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.post(
                f"/api/v1/products/{fake_id}/image",
                files={"file": ("test.svg", b"fake-svg-data", "image/svg+xml")},
                headers=headers,
            )
        assert resp.status_code == 400
        assert "not allowed" in resp.json()["detail"]

    def test_upload_product_image_too_large(self):
        db = _mock_db_with_execute()
        user = _make_user()
        db.get = AsyncMock(return_value=user)
        self._override_db(db)
        headers, _ = self._auth_headers()
        fake_id = str(uuid.uuid4())
        # 6MB file exceeds 5MB limit
        large_data = b"x" * (6 * 1024 * 1024)
        with TestClient(self.app) as client:
            resp = client.post(
                f"/api/v1/products/{fake_id}/image",
                files={"file": ("big.jpg", large_data, "image/jpeg")},
                headers=headers,
            )
        assert resp.status_code == 400
        assert "too large" in resp.json()["detail"].lower()

    def test_inventory_adjust_requires_auth(self):
        db = _mock_db_with_execute()
        self._override_db(db)
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.post(
                f"/api/v1/inventory/{fake_id}/adjust",
                json={
                    "quantity_change": 10,
                    "movement_type": "manual_add",
                    "reason": "test",
                },
            )
        assert resp.status_code == 401
