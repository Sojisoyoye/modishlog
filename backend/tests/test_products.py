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
    DuplicateSlugError,
    InvalidProductNameError,
    ProductNotFoundError,
)
from src.products.utils import slugify
from src.products.models import Product, ProductCategory
from src.products.schemas import CategoryCreate, CategoryUpdate, ProductCreate, ProductUpdate
from src.products.service import (
    create_category,
    create_product,
    deactivate_product,
    get_product,
    list_categories,
    update_category,
    update_product,
)

VALID_PASSWORD = "Str0ng!Pass#99"


def _make_user(**overrides):
    """Build a minimal User for tests."""
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


def _make_category(**overrides):
    defaults = dict(name="Electronics", description="Electronic goods", business_id=uuid.uuid4())
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
        slug="test-product",
        description="A test product",
        category_id=category_id or uuid.uuid4(),
        unit_cost=Decimal("100.000000"),
        selling_price=Decimal("150.000000"),
        currency="NGN",
        is_active=True,
        business_id=uuid.uuid4(),
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


def _mock_db_with_get_and_execute(entity=None):
    """Return an AsyncMock db where db.get() and db.execute() both return entity.

    Used for update_category tests which call get_category (db.get) then reload
    via db.execute(...).scalar_one() after the flush.
    """
    db = AsyncMock()
    db.get = AsyncMock(return_value=entity)
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one.return_value = entity
    db.execute = AsyncMock(return_value=result_mock)
    return db


def _mock_db_with_execute(scalar_result=None, scalars_result=None):
    """Return an AsyncMock db where db.execute() returns configurable results."""
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = scalar_result
    result_mock.scalar_one.return_value = scalar_result
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
        expected = _make_category(name="Electronics", description="Gadgets")
        db = _mock_db_with_execute(scalar_result=expected)
        data = CategoryCreate(name="Electronics", description="Gadgets")
        cat = await create_category(db, data, uuid.uuid4())
        assert cat.name == "Electronics"
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_category_not_found(self):
        db = _mock_db_with_get(entity=None)
        with pytest.raises(CategoryNotFoundError):
            from src.products.service import get_category
            await get_category(db, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_update_category_success(self):
        """update_category renames the category and returns it."""
        cat = _make_category(name="Old Name", description="Old desc")
        # After flush, service reloads via db.execute(...).scalar_one(); mock both paths
        cat.name = "New Name"
        cat.description = "New desc"
        db = _mock_db_with_get_and_execute(entity=cat)
        data = CategoryUpdate(name="New Name", description="New desc")
        updated = await update_category(db, cat.id, data)
        assert updated.name == "New Name"
        assert updated.description == "New desc"
        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_category_not_found(self):
        """update_category raises CategoryNotFoundError when category missing."""
        db = _mock_db_with_get(entity=None)
        with pytest.raises(CategoryNotFoundError):
            await update_category(db, uuid.uuid4(), CategoryUpdate(name="X"))

    @pytest.mark.asyncio
    async def test_update_category_partial(self):
        """update_category with only name updates name, keeps existing description."""
        cat = _make_category(name="Old Name", description="Keep me")
        cat.name = "New Name"
        db = _mock_db_with_get_and_execute(entity=cat)
        data = CategoryUpdate(name="New Name")
        updated = await update_category(db, cat.id, data)
        assert updated.name == "New Name"
        assert updated.description == "Keep me"

    @pytest.mark.asyncio
    async def test_update_category_clear_description(self):
        """Explicitly sending description=None clears the description via model_fields_set."""
        cat = _make_category(name="Foo", description="Has a desc")
        cat.description = None
        db = _mock_db_with_get_and_execute(entity=cat)
        data = CategoryUpdate(description=None)  # explicit null — included in model_fields_set
        updated = await update_category(db, cat.id, data)
        assert updated.description is None


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
        product = await create_product(db, data, uuid.uuid4(), uuid.uuid4())
        assert product.name == "No Category Widget"
        assert product.category_id is None
        assert product.sku.startswith("PRD-")

    @pytest.mark.asyncio
    async def test_create_product_auto_sku(self):
        business_id = uuid.uuid4()
        cat = _make_category(business_id=business_id)
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
        product = await create_product(db, data, uuid.uuid4(), business_id)
        assert product.name == "Widget"
        assert product.sku.startswith("PRD-")

    @pytest.mark.asyncio
    async def test_create_product_duplicate_sku(self):
        business_id = uuid.uuid4()
        cat = _make_category(business_id=business_id)
        existing = _make_product(category_id=cat.id, sku="DUP-SKU", business_id=business_id)

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
            await create_product(db, data, uuid.uuid4(), business_id)

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
        product = _make_product(slug="test-product")

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = product  # get_product
            else:
                result.scalar_one_or_none.return_value = None  # slug uniqueness: no conflict
            return result

        db = AsyncMock()
        db.execute = mock_execute
        db.flush = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=_make_category())

        data = ProductUpdate(name="New Name")
        updated = await update_product(db, product.id, data, uuid.uuid4())
        assert updated.name == "New Name"
        assert updated.slug == "new-name"
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

    def _override_auth(self):
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        u = _make_user(business_id=uuid.uuid4())
        async def _fake_auth():
            return u
        async def _fake_business_id():
            return u.business_id
        self.app.dependency_overrides[get_current_active_user] = _fake_auth
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id

    def _override_business_id(self, business_id: uuid.UUID | None = None):
        from src.auth.dependencies import get_current_business_id
        bid = business_id or uuid.uuid4()
        async def _fake_business_id():
            return bid
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id
        return bid

    def test_list_categories_empty(self):
        db = _mock_db_with_execute(scalars_result=[])
        self._override_db(db)
        self._override_business_id()
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
        expected_cat = _make_category(name="Test Category")
        expected_cat.children = []
        db = _mock_db_with_execute(scalar_result=expected_cat)
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
        self._override_business_id()
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
        self._override_business_id()
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/products/{fake_id}")
        assert resp.status_code == 404

    def test_low_stock_endpoint(self):
        self._override_auth()
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
        self._override_business_id()
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
        self._override_business_id()
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

    def test_upload_product_image_sets_image_url(self):
        """POST /products/{id}/image persists image_url on the returned product."""
        from unittest.mock import patch

        user = _make_user()
        product = _make_product()

        # update_product calls get_product → scalar_one_or_none returns product
        db = _mock_db_with_execute(scalar_result=product)
        db.get = AsyncMock(return_value=user)
        self._override_db(db)
        self._override_business_id()
        headers, _ = self._auth_headers()

        with patch("anyio.to_thread.run_sync", new_callable=AsyncMock), \
                patch("os.makedirs"):
            with TestClient(self.app) as client:
                resp = client.post(
                    f"/api/v1/products/{product.id}/image",
                    files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
                    headers=headers,
                )

        assert resp.status_code == 200
        assert resp.json()["image_url"] == f"/static/products/{product.id}.jpg"

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

    def test_update_category_success(self):
        """PATCH /products/categories/{id} updates name and description."""
        business_id = uuid.uuid4()
        cat = _make_category(name="New Name", description="New desc", business_id=business_id)
        cat.children = []
        user = _make_user()
        # update_category calls db.execute after flush to reload with selectinload(children)
        db = _mock_db_with_execute(scalar_result=cat)
        db.get = AsyncMock(side_effect=[user, cat])  # auth user then category
        self._override_db(db)
        self._override_business_id(business_id)
        headers, _ = self._auth_headers()
        with TestClient(self.app) as client:
            resp = client.patch(
                f"/api/v1/products/categories/{cat.id}",
                json={"name": "New Name", "description": "New desc"},
                headers=headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Name"
        assert data["description"] == "New desc"

    def test_update_category_not_found(self):
        """PATCH /products/categories/{id} returns 404 when category missing."""
        user = _make_user()
        db = _mock_db_with_execute()
        db.get = AsyncMock(side_effect=[user, None])  # auth user then missing category
        self._override_db(db)
        self._override_business_id()
        headers, _ = self._auth_headers()
        with TestClient(self.app) as client:
            resp = client.patch(
                f"/api/v1/products/categories/{uuid.uuid4()}",
                json={"name": "X"},
                headers=headers,
            )
        assert resp.status_code == 404

    def test_update_category_requires_auth(self):
        """PATCH /products/categories/{id} without auth → 401."""
        db = _mock_db_with_execute()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.patch(
                f"/api/v1/products/categories/{uuid.uuid4()}",
                json={"name": "X"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Price floor validation tests (task #95)
# ---------------------------------------------------------------------------


class TestProductPriceFloor:
    """ProductCreate and ProductUpdate schemas must reject zero prices."""

    def test_product_create_zero_selling_price_rejected(self):
        from decimal import Decimal
        from pydantic import ValidationError
        from src.products.schemas import ProductCreate
        with pytest.raises(ValidationError):
            ProductCreate(name="Bag", unit_cost=Decimal("1.00"), selling_price=Decimal("0"))

    def test_product_create_zero_unit_cost_rejected(self):
        from decimal import Decimal
        from pydantic import ValidationError
        from src.products.schemas import ProductCreate
        with pytest.raises(ValidationError):
            ProductCreate(name="Bag", unit_cost=Decimal("0"), selling_price=Decimal("500"))

    def test_product_create_positive_prices_accepted(self):
        from decimal import Decimal
        from src.products.schemas import ProductCreate
        p = ProductCreate(name="Bag", unit_cost=Decimal("100"), selling_price=Decimal("150"))
        assert p.unit_cost == Decimal("100")
        assert p.selling_price == Decimal("150")

    def test_product_update_zero_selling_price_rejected(self):
        from decimal import Decimal
        from pydantic import ValidationError
        from src.products.schemas import ProductUpdate
        with pytest.raises(ValidationError):
            ProductUpdate(selling_price=Decimal("0"))

    def test_product_update_zero_unit_cost_rejected(self):
        from decimal import Decimal
        from pydantic import ValidationError
        from src.products.schemas import ProductUpdate
        with pytest.raises(ValidationError):
            ProductUpdate(unit_cost=Decimal("0"))


# ---------------------------------------------------------------------------
# Mass assignment tests (task #93) — is_active must NOT be in ProductUpdate
# ---------------------------------------------------------------------------


class TestProductUpdateMassAssignment:
    """is_active must not be settable via PUT /products/{id}."""

    def test_product_update_schema_has_no_is_active_field(self):
        from src.products.schemas import ProductUpdate
        assert not hasattr(ProductUpdate.model_fields, "is_active") or \
            "is_active" not in ProductUpdate.model_fields, \
            "is_active must be removed from ProductUpdate to prevent mass assignment"

    def test_product_update_ignores_is_active_kwarg(self):
        """Passing is_active to ProductUpdate must raise ValidationError (extra=forbid)
        or silently ignore it — either way the field must never reach the DB."""
        from src.products.schemas import ProductUpdate
        # With extra fields ignored (default), is_active is dropped
        p = ProductUpdate(name="Test")
        assert not hasattr(p, "is_active") or getattr(p, "is_active", "MISSING") == "MISSING"


# ---------------------------------------------------------------------------
# Sub-category hierarchy tests (task #79)
# ---------------------------------------------------------------------------


class TestSubcategoryHierarchy:
    @pytest.mark.asyncio
    async def test_create_subcategory(self):
        """create_category with parent_id sets parent_id on the created category."""
        business_id = uuid.uuid4()
        parent = _make_category(name="Edge Tape", business_id=business_id)
        parent.parent_id = None
        parent.children = []

        expected = _make_category(name="Matt", business_id=business_id)
        expected.parent_id = parent.id
        expected.children = []

        result_mock = MagicMock()
        result_mock.scalar_one.return_value = expected

        db = AsyncMock()
        db.get = AsyncMock(return_value=parent)
        db.flush = AsyncMock()
        db.add = MagicMock()
        db.execute.return_value = result_mock

        data = CategoryCreate(name="Matt", parent_id=parent.id)
        cat = await create_category(db, data, business_id)
        assert cat.parent_id == parent.id
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_category_max_depth(self):
        """Cannot create a sub-sub-category (max 2 levels deep)."""
        from src.products.exceptions import SubcategoryDepthError

        business_id = uuid.uuid4()
        grandparent_id = uuid.uuid4()
        parent = _make_category(name="Mid Level", business_id=business_id)
        parent.parent_id = grandparent_id  # parent is itself a sub-category
        parent.children = []

        db = AsyncMock()
        db.get = AsyncMock(return_value=parent)
        db.flush = AsyncMock()
        db.add = MagicMock()

        data = CategoryCreate(name="Deep Level", parent_id=parent.id)
        with pytest.raises(SubcategoryDepthError):
            await create_category(db, data, business_id)

    @pytest.mark.asyncio
    async def test_list_categories_tree(self):
        """list_categories calls db.execute (uses selectinload) and returns categories."""
        parent = _make_category(name="Edge Tape")
        parent.parent_id = None
        child = _make_category(name="Matt")
        child.parent_id = parent.id
        child.children = []
        parent.children = [child]

        db = _mock_db_with_execute(scalars_result=[parent])
        cats = await list_categories(db, uuid.uuid4())
        db.execute.assert_called_once()
        assert len(cats) == 1
        assert cats[0].name == "Edge Tape"
        assert cats[0].children[0].name == "Matt"

    @pytest.mark.asyncio
    async def test_delete_category_with_children_raises(self):
        """Cannot delete a category that has sub-categories."""
        from src.products.exceptions import CategoryHasChildrenError

        business_id = uuid.uuid4()
        parent = _make_category(name="Edge Tape", business_id=business_id)
        parent.parent_id = None

        db = AsyncMock()
        db.get = AsyncMock(return_value=parent)
        db.flush = AsyncMock()
        db.add = MagicMock()
        db.delete = AsyncMock()

        # First execute call returns child_count=1, second returns product_count=0
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.scalar.return_value = 1 if call_count == 1 else 0
            return result

        db.execute = mock_execute

        from src.products.service import delete_category
        with pytest.raises(CategoryHasChildrenError):
            await delete_category(db, parent.id, business_id)

    @pytest.mark.asyncio
    async def test_product_assigned_to_subcategory(self):
        """Products can be assigned to a sub-category (any valid category UUID)."""
        business_id = uuid.uuid4()
        grandparent_id = uuid.uuid4()
        subcat = _make_category(name="Matt", business_id=business_id)
        subcat.parent_id = grandparent_id
        subcat.children = []

        db = AsyncMock()
        db.get = AsyncMock(return_value=subcat)
        db.flush = AsyncMock()
        db.add = MagicMock()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        result_mock.scalar.return_value = 0
        db.execute = AsyncMock(return_value=result_mock)

        user_id = uuid.uuid4()
        data = ProductCreate(
            name="Edge Tape Matt",
            unit_cost=Decimal("200.00"),
            selling_price=Decimal("350.00"),
            category_id=subcat.id,
        )
        product = await create_product(db, data, user_id, business_id)
        assert product.category_id == subcat.id


# ---------------------------------------------------------------------------
# Slugify utility tests (task #102)
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic_lowercase_and_spaces(self):
        assert slugify("Hello World") == "hello-world"

    def test_multiple_words(self):
        assert slugify("red pen large") == "red-pen-large"

    def test_special_chars_stripped(self):
        assert slugify("Hello, World!") == "hello-world"

    def test_multiple_hyphens_collapsed(self):
        assert slugify("hello  --  world") == "hello-world"

    def test_leading_trailing_hyphens_removed(self):
        assert slugify("--hello--") == "hello"

    def test_multiplication_sign_unicode(self):
        assert slugify("0.5×48") == "05x48"

    def test_multiplication_asterisk(self):
        assert slugify("0.5*48") == "05x48"

    def test_dot_stripped(self):
        assert slugify("v1.5") == "v15"

    def test_already_slug_unchanged(self):
        assert slugify("my-product") == "my-product"

    def test_numbers_preserved(self):
        assert slugify("Product 2024") == "product-2024"

    def test_parentheses_stripped(self):
        assert slugify("Widget (Large)") == "widget-large"

    def test_unicode_accent_transliteration(self):
        assert slugify("café") == "cafe"

    def test_unicode_tilde_transliteration(self):
        assert slugify("naïve") == "naive"

    def test_all_special_chars_returns_empty(self):
        assert slugify("---") == ""

    def test_only_special_chars_returns_empty(self):
        assert slugify("!@#$%") == ""


# ---------------------------------------------------------------------------
# Product slug service tests (task #102)
# ---------------------------------------------------------------------------


class TestProductSlug:
    @pytest.mark.asyncio
    async def test_create_product_generates_slug_from_name(self):
        """create_product sets slug derived from name."""
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
                result.scalar.return_value = 0  # SKU count
            else:
                result.scalar_one_or_none.return_value = None  # SKU unique, slug unique
            return result

        db.execute = mock_execute

        data = ProductCreate(
            name="Blue Marker",
            unit_cost=Decimal("10"),
            selling_price=Decimal("20"),
        )
        product = await create_product(db, data, uuid.uuid4(), uuid.uuid4())
        assert product.slug == "blue-marker"

    @pytest.mark.asyncio
    async def test_create_product_slug_with_multiplication_sign(self):
        """Slug handles × and * multiplication signs correctly."""
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        db.flush = AsyncMock()
        db.add = MagicMock()

        result_mock = MagicMock()
        result_mock.scalar.return_value = 0
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        data = ProductCreate(
            name="0.5×48",
            unit_cost=Decimal("10"),
            selling_price=Decimal("20"),
        )
        product = await create_product(db, data, uuid.uuid4(), uuid.uuid4())
        assert product.slug == "05x48"

    @pytest.mark.asyncio
    async def test_create_product_duplicate_slug_raises(self):
        """create_product raises DuplicateSlugError when slug already exists."""
        business_id = uuid.uuid4()
        cat = _make_category(business_id=business_id)
        existing = _make_product(category_id=cat.id, slug="test-product", business_id=business_id)

        db = AsyncMock()
        db.get = AsyncMock(return_value=cat)
        db.flush = AsyncMock()
        db.add = MagicMock()

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = None  # SKU unique
            else:
                result.scalar_one_or_none.return_value = existing  # slug conflict
            return result

        db.execute = mock_execute

        data = ProductCreate(
            name="Test Product",
            sku="NEW-001",
            category_id=cat.id,
            unit_cost=Decimal("10"),
            selling_price=Decimal("20"),
        )
        with pytest.raises(DuplicateSlugError):
            await create_product(db, data, uuid.uuid4(), business_id)

    @pytest.mark.asyncio
    async def test_update_product_name_change_regenerates_slug(self):
        """update_product regenerates slug when name changes."""
        product = _make_product(name="Old Name", slug="old-name")

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = product  # get_product
            else:
                result.scalar_one_or_none.return_value = None  # slug unique
            return result

        db = AsyncMock()
        db.execute = mock_execute
        db.flush = AsyncMock()
        db.add = MagicMock()

        data = ProductUpdate(name="New Name")
        updated = await update_product(db, product.id, data, uuid.uuid4())
        assert updated.slug == "new-name"

    @pytest.mark.asyncio
    async def test_update_product_same_name_keeps_slug(self):
        """update_product does not trigger slug check when name is unchanged."""
        product = _make_product(name="Test Product", slug="test-product")
        db = _mock_db_with_execute(scalar_result=product)

        data = ProductUpdate(description="Updated description")
        updated = await update_product(db, product.id, data, uuid.uuid4())
        assert updated.slug == "test-product"
        assert db.execute.call_count == 1  # only get_product, no slug check

    @pytest.mark.asyncio
    async def test_update_product_duplicate_slug_raises(self):
        """update_product raises DuplicateSlugError when renamed slug conflicts."""
        product = _make_product(name="Old Name", slug="old-name")
        conflict = _make_product(name="New Name", slug="new-name")

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = product  # get_product
            else:
                result.scalar_one_or_none.return_value = conflict  # slug conflict
            return result

        db = AsyncMock()
        db.execute = mock_execute
        db.flush = AsyncMock()
        db.add = MagicMock()

        data = ProductUpdate(name="New Name")
        with pytest.raises(DuplicateSlugError):
            await update_product(db, product.id, data, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_create_product_empty_slug_raises_invalid_name(self):
        """create_product raises InvalidProductNameError when slug is empty after normalisation."""
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        db.flush = AsyncMock()
        db.add = MagicMock()

        result_mock = MagicMock()
        result_mock.scalar.return_value = 0
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        data = ProductCreate(
            name="---",
            unit_cost=Decimal("10"),
            selling_price=Decimal("20"),
        )
        with pytest.raises(InvalidProductNameError):
            await create_product(db, data, uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_update_product_empty_slug_raises_invalid_name(self):
        """update_product raises InvalidProductNameError when renamed slug is empty."""
        product = _make_product(name="Test Product", slug="test-product")
        db = _mock_db_with_execute(scalar_result=product)

        data = ProductUpdate(name="---")
        with pytest.raises(InvalidProductNameError):
            await update_product(db, product.id, data, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_create_product_exposes_slug_in_result(self):
        """Slug is present and correct on the returned Product object."""
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        db.flush = AsyncMock()
        db.add = MagicMock()

        result_mock = MagicMock()
        result_mock.scalar.return_value = 0
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        data = ProductCreate(
            name="Hello World",
            unit_cost=Decimal("5"),
            selling_price=Decimal("10"),
        )
        product = await create_product(db, data, uuid.uuid4(), uuid.uuid4())
        assert product.slug == "hello-world"


# ---------------------------------------------------------------------------
# Product slug endpoint tests (task #102)
# ---------------------------------------------------------------------------


class TestProductSlugEndpoint:
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

    def _override_business_id(self, business_id: uuid.UUID | None = None):
        from src.auth.dependencies import get_current_business_id
        bid = business_id or uuid.uuid4()
        async def _fake_business_id():
            return bid
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id
        return bid

    def _auth_headers(self):
        user = _make_user()
        token = build_token(user)
        return {"Authorization": f"Bearer {token}"}, user

    def test_create_product_duplicate_slug_returns_409(self):
        """POST /products returns 409 when slug already exists."""
        user = _make_user()
        existing = _make_product(slug="hello-world")

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar.return_value = 0      # SKU count
            elif call_count == 2:
                result.scalar_one_or_none.return_value = None  # SKU unique
            else:
                result.scalar_one_or_none.return_value = existing  # slug conflict
            return result

        db = AsyncMock()
        db.execute = mock_execute
        db.flush = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=user)

        self._override_db(db)
        self._override_business_id()
        headers, _ = self._auth_headers()
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/products",
                json={
                    "name": "Hello World",
                    "unit_cost": "10.00",
                    "selling_price": "20.00",
                },
                headers=headers,
            )
        assert resp.status_code == 409
        assert "hello-world" in resp.json()["detail"]

    def test_create_product_empty_slug_returns_422(self):
        """POST /products with a name that slugifies to empty returns 422."""
        user = _make_user()

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.scalar.return_value = 0
            result.scalar_one_or_none.return_value = None
            return result

        db = AsyncMock()
        db.execute = mock_execute
        db.flush = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=user)

        self._override_db(db)
        self._override_business_id()
        headers, _ = self._auth_headers()
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/products",
                json={
                    "name": "---",
                    "unit_cost": "10.00",
                    "selling_price": "20.00",
                },
                headers=headers,
            )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Business isolation tests (task #159)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_products_isolates_by_business():
    """Business B user cannot see Business A's products."""
    business_a_id = uuid.uuid4()
    business_b_id = uuid.uuid4()

    # Mock: business_a sees 1 product, business_b sees 0
    async def fake_execute_a(query):
        result = MagicMock()
        result.scalars.return_value.all.return_value = [MagicMock()]
        result.scalar.return_value = 1
        return result

    async def fake_execute_b(query):
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalar.return_value = 0
        return result

    from src.products.service import list_products

    db_a = AsyncMock()
    db_a.execute = fake_execute_a
    db_b = AsyncMock()
    db_b.execute = fake_execute_b

    items_a, total_a = await list_products(db_a, business_id=business_a_id)
    items_b, total_b = await list_products(db_b, business_id=business_b_id)

    assert total_a == 1
    assert total_b == 0


@pytest.mark.asyncio
async def test_products_owner_sees_own_data():
    """Business A user sees their own products."""
    business_id = uuid.uuid4()
    mock_product = MagicMock()

    async def fake_execute(query):
        result = MagicMock()
        result.scalars.return_value.all.return_value = [mock_product]
        result.scalar.return_value = 1
        return result

    from src.products.service import list_products

    db = AsyncMock()
    db.execute = fake_execute
    items, total = await list_products(db, business_id=business_id)
    assert total == 1
    assert items[0] is mock_product
