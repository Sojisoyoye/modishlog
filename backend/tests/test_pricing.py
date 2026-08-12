"""Tests for pricing domain: demand forecast, margin optimization, recommendations."""

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.auth.service import build_token
from src.core.security import get_password_hash
from src.pricing.exceptions import (
    ElasticityNotFoundError,
    MixTargetSumError,
    RecommendationExpiredError,
    RecommendationNotFoundError,
)
from src.pricing.models import (
    DemandElasticity,
    MarginTarget,
    PricingRecommendation,
    ProductMixTarget,
    RecommendationStatus,
)
from src.products.models import Product, ProductCategory
import src.suppliers.models  # noqa: F401 — register Supplier mapper for PurchaseOrder

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


def _make_product(
    name="Widget A",
    sku="WDG-001",
    unit_cost=Decimal("1000.000000"),
    selling_price=Decimal("1500.000000"),
    **overrides,
):
    defaults = dict(
        name=name,
        sku=sku,
        unit_cost=unit_cost,
        selling_price=selling_price,
        currency="NGN",
        is_active=True,
        category_id=uuid.uuid4(),
    )
    defaults.update(overrides)
    p = Product(**defaults)
    p.id = overrides.get("id", uuid.uuid4())
    p.created_at = datetime.now(timezone.utc)
    p.updated_at = datetime.now(timezone.utc)
    return p


def _make_elasticity(product_id=None, **overrides):
    defaults = dict(
        product_id=product_id or uuid.uuid4(),
        elasticity_coefficient=Decimal("-1.0000"),
        r_squared=Decimal("0.8500"),
        data_points_used=50,
        calculation_date=date.today(),
        price_range_min=Decimal("1000.000000"),
        price_range_max=Decimal("2000.000000"),
        demand_curve_data=None,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    e = DemandElasticity(**defaults)
    e.id = overrides.get("id", uuid.uuid4())
    return e


def _make_recommendation(product_id=None, **overrides):
    defaults = dict(
        product_id=product_id or uuid.uuid4(),
        current_price=Decimal("1500.000000"),
        recommended_price=Decimal("1650.000000"),
        expected_demand_change_pct=Decimal("-10.00"),
        expected_revenue_change_pct=Decimal("10.00"),
        expected_margin_change_pct=Decimal("5.00"),
        confidence=Decimal("75.00"),
        reasoning="Test recommendation",
        status=RecommendationStatus.PENDING,
        applied_at=None,
        applied_by=None,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    r = PricingRecommendation(**defaults)
    r.id = overrides.get("id", uuid.uuid4())
    return r


def _mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


def _mock_db_with_execute(scalar_result=None, scalars_result=None):
    db = _mock_db()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = scalar_result
    result_mock.scalar.return_value = scalar_result
    if scalars_result is not None:
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = scalars_result
        result_mock.scalars.return_value = scalars_mock
    db.execute = AsyncMock(return_value=result_mock)
    return db


# ---------------------------------------------------------------------------
# Price Elasticity Impact
# ---------------------------------------------------------------------------


class TestPriceElasticityImpact:
    @pytest.mark.asyncio
    async def test_impact_with_default_elasticity(self):
        from src.pricing.service import calculate_price_elasticity_impact

        product = _make_product(selling_price=Decimal("1000.000000"))
        db = _mock_db()
        # First execute: product lookup, second: elasticity lookup
        product_result = MagicMock()
        product_result.scalar_one_or_none.return_value = product
        elasticity_result = MagicMock()
        elasticity_result.scalar_one_or_none.return_value = None  # default elasticity

        db.execute = AsyncMock(side_effect=[product_result, elasticity_result])

        result = await calculate_price_elasticity_impact(
            db, product.id, Decimal("1100.000000")
        )

        assert result["price_change_pct"] == 0.1  # 10% increase
        # Default elasticity -1.0: demand impact = -1.0 * 0.1 = -0.1
        assert result["demand_impact_pct"] == -0.1
        assert result["projected_demand_multiplier"] == 0.9

    @pytest.mark.asyncio
    async def test_impact_with_custom_elasticity(self):
        from src.pricing.service import calculate_price_elasticity_impact

        product = _make_product(selling_price=Decimal("1000.000000"))
        elasticity = _make_elasticity(
            product_id=product.id,
            elasticity_coefficient=Decimal("-0.5000"),
        )
        db = _mock_db()
        product_result = MagicMock()
        product_result.scalar_one_or_none.return_value = product
        elasticity_result = MagicMock()
        elasticity_result.scalar_one_or_none.return_value = elasticity

        db.execute = AsyncMock(side_effect=[product_result, elasticity_result])

        result = await calculate_price_elasticity_impact(
            db, product.id, Decimal("1100.000000")
        )

        # -0.5 * 0.1 = -0.05
        assert result["demand_impact_pct"] == -0.05
        assert result["projected_demand_multiplier"] == 0.95


# ---------------------------------------------------------------------------
# Elasticity CRUD
# ---------------------------------------------------------------------------


class TestElasticityCRUD:
    @pytest.mark.asyncio
    async def test_get_elasticity_not_found(self):
        from src.pricing.service import get_elasticity

        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(ElasticityNotFoundError):
            await get_elasticity(db, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_elasticity_success(self):
        from src.pricing.service import get_elasticity

        e = _make_elasticity()
        db = _mock_db_with_execute(scalar_result=e)
        result = await get_elasticity(db, e.product_id)
        assert result.elasticity_coefficient == Decimal("-1.0000")

    @pytest.mark.asyncio
    async def test_update_elasticity_creates_new(self):
        from src.pricing.service import update_elasticity_config

        db = _mock_db_with_execute(scalar_result=None)
        result = await update_elasticity_config(
            db, uuid.uuid4(), Decimal("-0.5")
        )
        assert result.elasticity_coefficient == Decimal("-0.5")
        assert db.add.called

    @pytest.mark.asyncio
    async def test_update_elasticity_updates_existing(self):
        from src.pricing.service import update_elasticity_config

        e = _make_elasticity()
        db = _mock_db_with_execute(scalar_result=e)
        result = await update_elasticity_config(
            db, e.product_id, Decimal("-2.0")
        )
        assert result.elasticity_coefficient == Decimal("-2.0")


# ---------------------------------------------------------------------------
# SciPy Optimizer
# ---------------------------------------------------------------------------


class TestOptimizer:
    def test_optimize_prices_basic(self):
        from src.pricing.service import _optimize_prices

        products = [
            {
                "product_id": uuid.uuid4(),
                "unit_cost": Decimal("1000"),
                "selling_price": Decimal("1200"),  # 16.7% margin, below 35%
                "avg_daily_sales": 10,
                "elasticity": -1.0,
            },
        ]
        result = _optimize_prices(products, target_margin=0.35)
        assert len(result) == 1
        # Optimized price should be higher to achieve 35% margin
        assert result[0]["optimized_price"] > Decimal("1200")

    def test_optimize_prices_empty(self):
        from src.pricing.service import _optimize_prices

        result = _optimize_prices([], target_margin=0.35)
        assert result == []

    def test_optimize_prices_respects_bounds(self):
        from src.pricing.service import _optimize_prices

        products = [
            {
                "product_id": uuid.uuid4(),
                "unit_cost": Decimal("1000"),
                "selling_price": Decimal("1200"),
                "avg_daily_sales": 10,
                "elasticity": -1.0,
            },
        ]
        result = _optimize_prices(products, target_margin=0.35)
        # Should be between 1.1x and 3.0x unit cost
        price = float(result[0]["optimized_price"])
        assert price >= 1000 * 1.10
        assert price <= 1000 * 3.0


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


class TestRecommendations:
    @pytest.mark.asyncio
    async def test_get_recommendations_empty(self):
        from src.pricing.service import get_recommendations

        db = _mock_db_with_execute(scalars_result=[])
        result = await get_recommendations(db, business_id=uuid.uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_apply_recommendation_not_found(self):
        from src.pricing.service import apply_recommendation

        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(RecommendationNotFoundError):
            await apply_recommendation(db, uuid.uuid4(), uuid.uuid4(), business_id=uuid.uuid4())

    @pytest.mark.asyncio
    async def test_apply_recommendation_expired(self):
        from src.pricing.service import apply_recommendation

        rec = _make_recommendation(
            created_at=datetime.now(timezone.utc) - timedelta(days=60)
        )
        db = _mock_db_with_execute(scalar_result=rec)
        with pytest.raises(RecommendationExpiredError):
            await apply_recommendation(db, rec.id, uuid.uuid4(), business_id=uuid.uuid4())

    @pytest.mark.asyncio
    async def test_apply_recommendation_success(self):
        from src.pricing.service import apply_recommendation

        product = _make_product()
        rec = _make_recommendation(
            product_id=product.id,
            recommended_price=Decimal("1650.000000"),
        )

        db = _mock_db()
        # First: fetch recommendation, second: fetch product
        rec_result = MagicMock()
        rec_result.scalar_one_or_none.return_value = rec
        product_result = MagicMock()
        product_result.scalar_one_or_none.return_value = product

        db.execute = AsyncMock(side_effect=[rec_result, product_result])

        result = await apply_recommendation(db, rec.id, uuid.uuid4(), business_id=uuid.uuid4())
        assert result.status == RecommendationStatus.APPLIED
        assert result.applied_at is not None
        assert product.selling_price == Decimal("1650.000000")
        # PriceHistory was added
        assert db.add.called

    @pytest.mark.asyncio
    async def test_dismiss_recommendation(self):
        from src.pricing.service import dismiss_recommendation

        rec = _make_recommendation()
        db = _mock_db_with_execute(scalar_result=rec)
        result = await dismiss_recommendation(db, rec.id, business_id=uuid.uuid4())
        assert result.status == RecommendationStatus.REJECTED

    @pytest.mark.asyncio
    async def test_dismiss_recommendation_not_found(self):
        from src.pricing.service import dismiss_recommendation

        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(RecommendationNotFoundError):
            await dismiss_recommendation(db, uuid.uuid4(), business_id=uuid.uuid4())


# ---------------------------------------------------------------------------
# Margin Targets
# ---------------------------------------------------------------------------


class TestMarginTargets:
    @pytest.mark.asyncio
    async def test_set_margin_target(self):
        from src.pricing.schemas import MarginTargetCreate
        from src.pricing.service import set_margin_target

        db = _mock_db()
        db.execute = AsyncMock()
        data = MarginTargetCreate(
            target_margin_pct=Decimal("35.00"),
            min_margin_pct=Decimal("25.00"),
        )
        result = await set_margin_target(db, data, uuid.uuid4(), business_id=uuid.uuid4())
        assert result.target_margin_pct == Decimal("35.00")
        assert db.add.called

    @pytest.mark.asyncio
    async def test_get_margin_targets(self):
        from src.pricing.service import get_margin_targets

        targets = [MarginTarget(
            target_margin_pct=Decimal("35.00"),
            min_margin_pct=Decimal("25.00"),
            priority=1,
            set_by=uuid.uuid4(),
        )]
        targets[0].id = uuid.uuid4()
        db = _mock_db_with_execute(scalars_result=targets)
        result = await get_margin_targets(db, business_id=uuid.uuid4())
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_delete_margin_target_removes_it(self):
        from src.pricing.service import delete_margin_target

        target = MarginTarget(
            target_margin_pct=Decimal("35.00"),
            min_margin_pct=Decimal("25.00"),
            priority=1,
            set_by=uuid.uuid4(),
        )
        target.id = uuid.uuid4()
        business_id = uuid.uuid4()
        db = _mock_db_with_execute(scalar_result=target)

        await delete_margin_target(db, target.id, business_id=business_id)

        db.delete.assert_called_once_with(target)

    @pytest.mark.asyncio
    async def test_delete_margin_target_not_found_raises(self):
        from src.pricing.exceptions import MarginTargetNotFoundError
        from src.pricing.service import delete_margin_target

        db = _mock_db_with_execute(scalar_result=None)

        with pytest.raises(MarginTargetNotFoundError):
            await delete_margin_target(db, uuid.uuid4(), business_id=uuid.uuid4())


class TestMarginTargetResolution:
    """_pick_margin_target() / _resolve_target_margin() — Settings-
    configured MarginTarget rows take priority over ProductCategory.
    default_margin_pct, product-level beating category-level regardless
    of priority (priority only tie-breaks within the same specificity)."""

    def _product(self, category_id=None, category=None):
        product = Product(name="Widget", slug="widget", sku="SKU-1", selling_price=Decimal("100"), business_id=uuid.uuid4())
        product.id = uuid.uuid4()
        product.category_id = category_id
        product.category = category
        return product

    def _target(self, product_id=None, category_id=None, pct="35.00", min_pct="10.00", priority=1):
        t = MarginTarget(
            product_id=product_id,
            category_id=category_id,
            target_margin_pct=Decimal(pct),
            min_margin_pct=Decimal(min_pct),
            priority=priority,
            set_by=uuid.uuid4(),
        )
        t.id = uuid.uuid4()
        return t

    def test_product_level_target_wins_over_category(self):
        from src.pricing.service import _resolve_target_margin

        cat_id = uuid.uuid4()
        category = ProductCategory(name="Cat", business_id=uuid.uuid4())
        category.id = cat_id
        category.default_margin_pct = Decimal("0.50")
        category.parent = None
        product = self._product(category_id=cat_id, category=category)

        targets = [
            self._target(category_id=cat_id, pct="45.00"),
            self._target(product_id=product.id, pct="35.00"),
        ]

        assert _resolve_target_margin(product, targets) == Decimal("0.35")

    def test_category_level_target_wins_over_default_margin_pct(self):
        from src.pricing.service import _resolve_target_margin

        cat_id = uuid.uuid4()
        category = ProductCategory(name="Cat", business_id=uuid.uuid4())
        category.id = cat_id
        category.default_margin_pct = Decimal("0.50")
        category.parent = None
        product = self._product(category_id=cat_id, category=category)

        targets = [self._target(category_id=cat_id, pct="45.00")]

        assert _resolve_target_margin(product, targets) == Decimal("0.45")

    def test_priority_breaks_ties_among_same_specificity(self):
        from src.pricing.service import _resolve_target_margin

        product = self._product()
        targets = [
            self._target(product_id=product.id, pct="30.00", priority=1),
            self._target(product_id=product.id, pct="40.00", priority=5),
        ]

        assert _resolve_target_margin(product, targets) == Decimal("0.40")

    def test_no_matching_target_falls_back_to_category_default(self):
        from src.pricing.service import _resolve_target_margin

        cat_id = uuid.uuid4()
        category = ProductCategory(name="Cat", business_id=uuid.uuid4())
        category.id = cat_id
        category.default_margin_pct = Decimal("0.50")
        category.parent = None
        product = self._product(category_id=cat_id, category=category)

        other_product_target = [self._target(product_id=uuid.uuid4(), pct="99.00")]

        assert _resolve_target_margin(product, other_product_target) == Decimal("0.50")

    def test_no_target_no_category_default_falls_back_to_40_pct(self):
        from src.pricing.service import _resolve_target_margin

        product = self._product()
        assert _resolve_target_margin(product, []) == Decimal("0.40")

    def test_resolve_min_margin_reads_matched_targets_min_pct(self):
        from src.pricing.service import _resolve_min_margin

        product = self._product()
        targets = [self._target(product_id=product.id, pct="35.00", min_pct="25.00")]

        assert _resolve_min_margin(product, targets) == Decimal("0.25")

    def test_resolve_min_margin_none_when_no_target_matches(self):
        from src.pricing.service import _resolve_min_margin

        product = self._product()
        assert _resolve_min_margin(product, []) is None
        other = [self._target(product_id=uuid.uuid4(), min_pct="99.00")]
        assert _resolve_min_margin(product, other) is None

    def test_apply_min_margin_floor_bumps_price_up_when_below_floor(self):
        from src.pricing.service import _apply_min_margin_floor

        # cost=15000, target-margin-derived suggestion=15000/0.60=25000,
        # but a 50% min margin floor requires 15000/0.50=30000
        result = _apply_min_margin_floor(Decimal("25000"), Decimal("15000"), Decimal("0.50"))
        assert result == Decimal("30000.000000")

    def test_apply_min_margin_floor_leaves_price_when_already_above_floor(self):
        from src.pricing.service import _apply_min_margin_floor

        # suggestion=30000 already clears a 20% floor (15000/0.80=18750)
        result = _apply_min_margin_floor(Decimal("30000"), Decimal("15000"), Decimal("0.20"))
        assert result == Decimal("30000")

    def test_apply_min_margin_floor_noop_when_none(self):
        from src.pricing.service import _apply_min_margin_floor

        assert _apply_min_margin_floor(Decimal("25000"), Decimal("15000"), None) == Decimal("25000")

    def test_apply_min_margin_floor_ignores_impossible_100pct_plus(self):
        from src.pricing.service import _apply_min_margin_floor

        # min_margin >= 100% can't produce a finite price — ignored rather
        # than dividing by zero/negative
        result = _apply_min_margin_floor(Decimal("25000"), Decimal("15000"), Decimal("1.00"))
        assert result == Decimal("25000")


# ---------------------------------------------------------------------------
# Demand Forecast Helpers
# ---------------------------------------------------------------------------


class TestDemandForecastHelpers:
    @pytest.mark.asyncio
    async def test_fetch_sales_insufficient_data(self):
        from src.pricing.exceptions import InsufficientPriceDataError
        from src.pricing.service import _fetch_sales_history

        db = _mock_db()
        result_mock = MagicMock()
        result_mock.all.return_value = [(date.today(), 5)]  # only 1 point
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(InsufficientPriceDataError):
            await _fetch_sales_history(db, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_fetch_sales_success(self):
        from src.pricing.service import _fetch_sales_history

        rows = [
            (date.today() - timedelta(days=i), 10 + i)
            for i in range(15)
        ]
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.all.return_value = rows
        db.execute = AsyncMock(return_value=result_mock)

        df = await _fetch_sales_history(db, uuid.uuid4())
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 15
        assert "ds" in df.columns
        assert "y" in df.columns

    @pytest.mark.asyncio
    async def test_demand_forecast_full_pipeline(self):
        from src.pricing.service import calculate_demand_forecast

        rows = [
            (date.today() - timedelta(days=i), 10 + i % 5)
            for i in range(30)
        ]
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.all.return_value = rows
        db.execute = AsyncMock(return_value=result_mock)

        # Mock Prophet
        mock_model = MagicMock()
        mock_model.history = pd.DataFrame({
            "ds": pd.date_range("2026-01-01", periods=30, freq="D"),
        })
        forecast_df = pd.DataFrame({
            "ds": pd.date_range("2026-01-01", periods=40, freq="D"),
            "yhat": [12.0] * 40,
            "yhat_lower": [8.0] * 40,
            "yhat_upper": [16.0] * 40,
        })
        mock_model.make_future_dataframe.return_value = forecast_df[["ds"]]
        mock_model.predict.return_value = forecast_df

        with patch("src.pricing.service._train_demand_model", return_value=mock_model):
            result = await calculate_demand_forecast(
                db, uuid.uuid4(), horizon_days=10
            )

        assert result["horizon_days"] == 10
        assert len(result["forecasts"]) == 10
        assert result["total_projected_demand"] > 0


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


BUSINESS_ID = uuid.uuid4()


class TestPricingEndpoints:
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
        u = _make_user(business_id=BUSINESS_ID)
        async def _fake_auth():
            return u
        async def _fake_business_id():
            return BUSINESS_ID
        self.app.dependency_overrides[get_current_active_user] = _fake_auth
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id

    def test_recommendations_empty(self):
        self._override_auth()
        db = _mock_db_with_execute(scalars_result=[])
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/pricing/recommendations")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_generate_recommendations_requires_auth(self):
        db = _mock_db()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/pricing/recommendations/generate",
                json={"target_margin": "35.00"},
            )
        assert resp.status_code == 401

    def test_apply_recommendation_requires_auth(self):
        db = _mock_db()
        self._override_db(db)
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.post(f"/api/v1/pricing/recommendations/{fake_id}/apply")
        assert resp.status_code == 401

    def test_elasticity_not_found(self):
        self._override_auth()
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/pricing/elasticity/{fake_id}")
        assert resp.status_code == 404

    def test_configure_elasticity_requires_auth(self):
        db = _mock_db()
        self._override_db(db)
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.post(
                f"/api/v1/pricing/configure-elasticity/{fake_id}",
                json={"elasticity_coefficient": "-0.5"},
            )
        assert resp.status_code == 401

    def test_suggest_endpoint_passes_variant_id_through(self):
        """The /suggest/{product_id} endpoint must forward a request's
        variant_id to compute_suggestion() — otherwise the variant-scoped
        WHERE clause added for task 171 is unreachable from the real API
        contract, not just the service-layer function signature."""
        from src.pricing.models import PriceSuggestion

        self._override_auth()
        db = _mock_db()
        self._override_db(db)
        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()

        fake_suggestion = PriceSuggestion(
            product_id=product_id,
            variant_id=variant_id,
            unit_cost_ngn=Decimal("14000"),
            fx_rate_used=Decimal("1700"),
            target_margin_pct=Decimal("0.40"),
            suggested_price_ngn=Decimal("23333.33"),
            current_catalog_price_ngn=None,
            suggested_at=datetime.now(timezone.utc),
        )
        fake_suggestion.id = uuid.uuid4()

        with patch(
            "src.pricing.router.compute_suggestion",
            new_callable=AsyncMock,
            return_value=fake_suggestion,
        ) as mock_compute:
            headers, _ = self._auth_headers()
            with TestClient(self.app) as client:
                resp = client.post(
                    f"/api/v1/pricing/suggest/{product_id}",
                    headers=headers,
                    json={"variant_id": str(variant_id)},
                )

        assert resp.status_code == 201
        assert resp.json()["variant_id"] == str(variant_id)
        mock_compute.assert_awaited_once()
        _, kwargs = mock_compute.call_args
        assert kwargs["variant_id"] == variant_id

    def test_suggestion_history_endpoint_returns_422_for_mismatched_variant(self):
        """GET /suggest/{product_id}/history?variant_id=... must convert
        get_suggestion_history()'s PricingSuggestionError (raised when
        variant_id doesn't belong to product_id) to a 422 — mirrors
        compute_suggestion_endpoint's identical try/except. Exercised at
        the router layer, not just get_suggestion_history() directly, so
        a miswired except clause (wrong status, wrong exception type, or
        an unhandled 500) would actually be caught."""
        from src.pricing.exceptions import PricingSuggestionError

        self._override_auth()
        db = _mock_db()
        self._override_db(db)
        product_id = uuid.uuid4()
        foreign_variant_id = uuid.uuid4()

        with patch(
            "src.pricing.router.get_suggestion_history",
            new_callable=AsyncMock,
            side_effect=PricingSuggestionError(
                product_id, "variant does not belong to this product"
            ),
        ):
            headers, _ = self._auth_headers()
            with TestClient(self.app) as client:
                resp = client.get(
                    f"/api/v1/pricing/suggest/{product_id}/history",
                    headers=headers,
                    params={"variant_id": str(foreign_variant_id)},
                )

        assert resp.status_code == 422

    def test_margin_targets_empty(self):
        self._override_auth()
        db = _mock_db_with_execute(scalars_result=[])
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/pricing/margins/target")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_margin_target_requires_auth(self):
        db = _mock_db()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/pricing/margins/target",
                json={
                    "target_margin_pct": "35.00",
                    "min_margin_pct": "25.00",
                },
            )
        assert resp.status_code == 401

    def test_dismiss_recommendation_not_found(self):
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        headers, user = self._auth_headers()
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.post(
                f"/api/v1/pricing/recommendations/{fake_id}/dismiss",
                headers=headers,
            )
        assert resp.status_code == 404

    def test_mix_targets_requires_auth(self):
        db = _mock_db()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/pricing/mix-targets",
                json={"targets": []},
            )
        assert resp.status_code == 401

    def test_mix_targets_rejects_bad_sum(self):
        db = _mock_db()
        self._override_db(db)
        headers, user = self._auth_headers()
        cat1 = str(uuid.uuid4())
        cat2 = str(uuid.uuid4())
        with TestClient(self.app) as client:
            # upsert_mix_targets will raise MixTargetSumError => 400
            resp = client.post(
                "/api/v1/pricing/mix-targets",
                headers=headers,
                json={
                    "targets": [
                        {"category_id": cat1, "target_pct": "60.00"},
                        {"category_id": cat2, "target_pct": "30.00"},
                    ]
                },
            )
        assert resp.status_code == 400
        assert "sum to 100" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Product Mix Target Service Tests
# ---------------------------------------------------------------------------


class TestMixTargets:
    @pytest.mark.asyncio
    async def test_upsert_rejects_sum_not_100(self):
        """Target percentages that don't sum to 100 must be rejected."""
        from src.pricing.service import upsert_mix_targets

        db = _mock_db()
        targets = [
            {"category_id": uuid.uuid4(), "target_pct": Decimal("60.00")},
            {"category_id": uuid.uuid4(), "target_pct": Decimal("30.00")},
        ]
        with pytest.raises(MixTargetSumError):
            await upsert_mix_targets(db, targets)

    @pytest.mark.asyncio
    async def test_upsert_accepts_sum_100(self):
        """Valid targets summing to 100 should be upserted."""
        from src.pricing.service import upsert_mix_targets

        cat1_id = uuid.uuid4()
        cat2_id = uuid.uuid4()

        db = _mock_db()
        # Each target lookup returns None (no existing), so new records created
        none_result = MagicMock()
        none_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=none_result)

        targets = [
            {"category_id": cat1_id, "target_pct": Decimal("60.00")},
            {"category_id": cat2_id, "target_pct": Decimal("40.00")},
        ]
        result = await upsert_mix_targets(db, targets)
        assert len(result) == 2
        assert db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self):
        """Existing target should be updated, not duplicated."""
        from src.pricing.service import upsert_mix_targets

        cat_id = uuid.uuid4()
        existing = ProductMixTarget(
            category_id=cat_id,
            target_pct=Decimal("50.00"),
        )
        existing.id = uuid.uuid4()
        existing.created_at = datetime.now(timezone.utc)
        existing.updated_at = datetime.now(timezone.utc)

        db = _mock_db()
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = existing
        none_result = MagicMock()
        none_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(side_effect=[existing_result, none_result])

        targets = [
            {"category_id": cat_id, "target_pct": Decimal("70.00")},
            {"category_id": uuid.uuid4(), "target_pct": Decimal("30.00")},
        ]
        result = await upsert_mix_targets(db, targets)
        assert len(result) == 2
        # First was updated in-place
        assert result[0].target_pct == Decimal("70.00")
        # Second was added
        assert db.add.call_count == 1


class TestMixStatus:
    @pytest.mark.asyncio
    async def test_mix_status_calculation(self):
        """Mix status should correctly compute actual vs target percentages."""
        from src.pricing.service import get_mix_status

        cat1_id = uuid.uuid4()
        cat2_id = uuid.uuid4()

        db = _mock_db()

        # Revenue rows: cat1 has 7000, cat2 has 3000 => 70% / 30%
        revenue_result = MagicMock()
        revenue_result.all.return_value = [
            (cat1_id, "Electronics", Decimal("7000")),
            (cat2_id, "Clothing", Decimal("3000")),
        ]

        # Targets: cat1=60%, cat2=40%
        target1 = ProductMixTarget(
            category_id=cat1_id, target_pct=Decimal("60.00")
        )
        target1.id = uuid.uuid4()
        target2 = ProductMixTarget(
            category_id=cat2_id, target_pct=Decimal("40.00")
        )
        target2.id = uuid.uuid4()
        targets_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [target1, target2]
        targets_result.scalars.return_value = scalars_mock

        db.execute = AsyncMock(side_effect=[revenue_result, targets_result])

        result = await get_mix_status(db)
        assert len(result) == 2

        # cat1: actual 70%, target 60%, variance +10%
        cat1_status = next(s for s in result if s["category_id"] == cat1_id)
        assert cat1_status["actual_pct"] == Decimal("70.00")
        assert cat1_status["target_pct"] == Decimal("60.00")
        assert cat1_status["variance_pct"] == Decimal("10.00")

        # cat2: actual 30%, target 40%, variance -10%
        cat2_status = next(s for s in result if s["category_id"] == cat2_id)
        assert cat2_status["actual_pct"] == Decimal("30.00")
        assert cat2_status["target_pct"] == Decimal("40.00")
        assert cat2_status["variance_pct"] == Decimal("-10.00")


class TestMixDriftAlert:
    @pytest.mark.asyncio
    async def test_drift_alert_created_when_variance_exceeds_threshold(self):
        """An AI recommendation should be created when drift > 5%."""
        from src.pricing.service import check_mix_drift_alert

        cat1_id = uuid.uuid4()
        cat2_id = uuid.uuid4()

        db = _mock_db()

        # get_mix_status internal calls
        # 1. Revenue query
        revenue_result = MagicMock()
        revenue_result.all.return_value = [
            (cat1_id, "Electronics", Decimal("8000")),
            (cat2_id, "Clothing", Decimal("2000")),
        ]

        # 2. Targets query
        target1 = ProductMixTarget(
            category_id=cat1_id, target_pct=Decimal("50.00")
        )
        target1.id = uuid.uuid4()
        target2 = ProductMixTarget(
            category_id=cat2_id, target_pct=Decimal("50.00")
        )
        target2.id = uuid.uuid4()
        targets_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [target1, target2]
        targets_result.scalars.return_value = scalars_mock

        # 3. Dedup check: no existing recommendation
        dedup_result = MagicMock()
        dedup_result.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(
            side_effect=[revenue_result, targets_result, dedup_result]
        )

        await check_mix_drift_alert(db)

        # Should have added one AIRecommendation
        assert db.add.called
        added_obj = db.add.call_args[0][0]
        assert added_obj.reference_type == "mix_drift"
        assert "drift" in added_obj.title.lower()

    @pytest.mark.asyncio
    async def test_drift_alert_deduplicated(self):
        """No new alert if a pending mix_drift recommendation already exists."""
        from src.ai_engine.models import AIRecommendation
        from src.pricing.service import check_mix_drift_alert

        cat1_id = uuid.uuid4()

        db = _mock_db()

        # get_mix_status calls
        revenue_result = MagicMock()
        revenue_result.all.return_value = [
            (cat1_id, "Electronics", Decimal("10000")),
        ]

        target1 = ProductMixTarget(
            category_id=cat1_id, target_pct=Decimal("50.00")
        )
        target1.id = uuid.uuid4()
        targets_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [target1]
        targets_result.scalars.return_value = scalars_mock

        # Dedup check: existing pending recommendation
        existing_rec = MagicMock(spec=AIRecommendation)
        existing_rec.id = uuid.uuid4()
        dedup_result = MagicMock()
        dedup_result.scalar_one_or_none.return_value = existing_rec

        db.execute = AsyncMock(
            side_effect=[revenue_result, targets_result, dedup_result]
        )

        await check_mix_drift_alert(db)

        # Should NOT have added any new recommendation
        assert not db.add.called

    @pytest.mark.asyncio
    async def test_no_alert_when_within_threshold(self):
        """No alert when variance is within 5% threshold."""
        from src.pricing.service import check_mix_drift_alert

        cat1_id = uuid.uuid4()
        cat2_id = uuid.uuid4()

        db = _mock_db()

        # Revenue: 52%/48% against 50%/50% targets => 2% variance, under 5%
        revenue_result = MagicMock()
        revenue_result.all.return_value = [
            (cat1_id, "Electronics", Decimal("5200")),
            (cat2_id, "Clothing", Decimal("4800")),
        ]

        target1 = ProductMixTarget(
            category_id=cat1_id, target_pct=Decimal("50.00")
        )
        target1.id = uuid.uuid4()
        target2 = ProductMixTarget(
            category_id=cat2_id, target_pct=Decimal("50.00")
        )
        target2.id = uuid.uuid4()
        targets_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [target1, target2]
        targets_result.scalars.return_value = scalars_mock

        db.execute = AsyncMock(
            side_effect=[revenue_result, targets_result]
        )

        await check_mix_drift_alert(db)

        # No alert should be created
        assert not db.add.called


# ---------------------------------------------------------------------------
# Tests for PriceSuggestion engine (Task #76)
# ---------------------------------------------------------------------------


class TestPriceSuggestionEngine:
    """compute_suggestion uses lot-based weighted avg cost + live FX."""

    def _make_lot(self, product_id, units_remaining, unit_cost=None, unit_cost_ngn=None, fx_rate=None):
        from src.orders.models import OrderLineItem
        lot = MagicMock(spec=OrderLineItem)
        lot.product_id = product_id
        lot.units_remaining = Decimal(str(units_remaining))
        lot.unit_cost = Decimal(str(unit_cost or "10"))
        lot.unit_cost_ngn = Decimal(str(unit_cost_ngn)) if unit_cost_ngn else None
        return lot

    def _mock_execute_lots_then_product(self, lots_with_currency, catalog_price="20000"):
        """Return an async mock_execute that serves lots (call 1) then product (call 2)."""
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:  # join query returns (OrderLineItem, currency) tuples
                result.all.return_value = lots_with_currency
            else:  # product catalog price lookup
                p = MagicMock()
                p.selling_price = Decimal(str(catalog_price))
                result.scalar_one_or_none.return_value = p
            return result

        return mock_execute

    @pytest.mark.asyncio
    async def test_compute_suggestion_single_lot(self):
        """Single lot: suggested_price = unit_cost_ngn / (1 - margin)."""
        from src.pricing.service import compute_suggestion

        product_id = uuid.uuid4()
        lot = self._make_lot(product_id, units_remaining=10, unit_cost_ngn="14000")

        db = _mock_db()
        db.execute = self._mock_execute_lots_then_product([(lot, "USD")])

        with patch("src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock,
                   return_value=(Decimal("1700"), datetime.now(timezone.utc), True)):
            suggestion = await compute_suggestion(db, product_id, target_margin=Decimal("0.40"))

        # 14000 / (1 - 0.40) = 23333.33
        expected = Decimal("14000") / Decimal("0.60")
        assert abs(suggestion.suggested_price_ngn - expected) < Decimal("1")
        assert suggestion.product_id == product_id

    @pytest.mark.asyncio
    async def test_compute_suggestion_weighted_average(self):
        """Two lots: uses weighted average of unit_cost_ngn."""
        from src.pricing.service import compute_suggestion

        product_id = uuid.uuid4()
        lot1 = self._make_lot(product_id, units_remaining=10, unit_cost_ngn="14000")
        lot2 = self._make_lot(product_id, units_remaining=20, unit_cost_ngn="16000")

        db = _mock_db()
        db.execute = self._mock_execute_lots_then_product([(lot1, "USD"), (lot2, "USD")])

        with patch("src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock,
                   return_value=(Decimal("1700"), datetime.now(timezone.utc), True)):
            suggestion = await compute_suggestion(db, product_id, target_margin=Decimal("0.40"))

        # weighted avg = (14000*10 + 16000*20) / 30 = 460000/30 = 15333.33
        weighted = (Decimal("14000") * 10 + Decimal("16000") * 20) / 30
        expected = weighted / Decimal("0.60")
        assert abs(suggestion.unit_cost_ngn - weighted) < Decimal("1")
        assert abs(suggestion.suggested_price_ngn - expected) < Decimal("1")

    @pytest.mark.asyncio
    async def test_compute_suggestion_uses_live_fx_for_usd_lots(self):
        """USD lot with no unit_cost_ngn: falls back to unit_cost * live FX rate."""
        from src.pricing.service import compute_suggestion

        product_id = uuid.uuid4()
        lot = self._make_lot(product_id, units_remaining=5, unit_cost="10", unit_cost_ngn=None)

        db = _mock_db()
        db.execute = self._mock_execute_lots_then_product([(lot, "USD")])

        live_fx = Decimal("1750")
        with patch("src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock,
                   return_value=(live_fx, datetime.now(timezone.utc), False)):
            suggestion = await compute_suggestion(db, product_id, target_margin=Decimal("0.40"))

        # cost_ngn = unit_cost * fx_rate = 10 * 1750 = 17500
        expected_cost = Decimal("10") * live_fx
        assert abs(suggestion.unit_cost_ngn - expected_cost) < Decimal("1")
        assert suggestion.fx_rate_used == live_fx

    @pytest.mark.asyncio
    async def test_compute_suggestion_ngn_order_uses_unit_cost_directly(self):
        """NGN order with no unit_cost_ngn: uses unit_cost directly (no FX multiply)."""
        from src.pricing.service import compute_suggestion

        product_id = uuid.uuid4()
        lot = self._make_lot(product_id, units_remaining=10, unit_cost="5000", unit_cost_ngn=None)

        db = _mock_db()
        db.execute = self._mock_execute_lots_then_product([(lot, "NGN")])

        live_fx = Decimal("1600")
        with patch("src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock,
                   return_value=(live_fx, datetime.now(timezone.utc), True)):
            suggestion = await compute_suggestion(db, product_id, target_margin=Decimal("0.40"))

        # cost_ngn should be 5000, NOT 5000 * 1600
        assert abs(suggestion.unit_cost_ngn - Decimal("5000")) < Decimal("1")

    @pytest.mark.asyncio
    async def test_compute_suggestion_no_active_lots_raises(self):
        """No active lots → PricingError raised."""
        from src.pricing.service import compute_suggestion
        from src.pricing.exceptions import PricingSuggestionError

        product_id = uuid.uuid4()
        db = _mock_db()
        result = MagicMock()
        result.all.return_value = []
        db.execute = AsyncMock(return_value=result)

        with pytest.raises(PricingSuggestionError):
            await compute_suggestion(db, product_id, target_margin=Decimal("0.40"))

    @pytest.mark.asyncio
    async def test_compute_suggestion_target_margin_override(self):
        """35% margin override produces a lower suggested price than 40%."""
        from src.pricing.service import compute_suggestion

        product_id = uuid.uuid4()
        lot = self._make_lot(product_id, units_remaining=10, unit_cost_ngn="14000")

        db = _mock_db()
        db.execute = self._mock_execute_lots_then_product([(lot, "USD")])

        with patch("src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock,
                   return_value=(Decimal("1700"), datetime.now(timezone.utc), True)):
            s40 = await compute_suggestion(db, product_id, target_margin=Decimal("0.40"))

        db.execute = self._mock_execute_lots_then_product([(lot, "USD")])
        with patch("src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock,
                   return_value=(Decimal("1700"), datetime.now(timezone.utc), True)):
            s35 = await compute_suggestion(db, product_id, target_margin=Decimal("0.35"))

        assert s35.suggested_price_ngn < s40.suggested_price_ngn
        assert s35.target_margin_pct == Decimal("0.35")

    def test_suggest_request_rejects_margin_ge_1(self):
        """target_margin_pct >= 1 must fail schema validation."""
        from pydantic import ValidationError
        from src.pricing.schemas import SuggestRequest

        with pytest.raises(ValidationError):
            SuggestRequest(target_margin_pct=Decimal("1.0"))

        with pytest.raises(ValidationError):
            SuggestRequest(target_margin_pct=Decimal("1.5"))

    def test_suggest_request_rejects_margin_le_0(self):
        """target_margin_pct <= 0 must fail schema validation."""
        from pydantic import ValidationError
        from src.pricing.schemas import SuggestRequest

        with pytest.raises(ValidationError):
            SuggestRequest(target_margin_pct=Decimal("0"))

        with pytest.raises(ValidationError):
            SuggestRequest(target_margin_pct=Decimal("-0.1"))

    @pytest.mark.asyncio
    async def test_min_margin_pct_floors_the_suggested_price(self):
        """A MarginTarget's min_margin_pct must actually change the
        suggested price, not just get stored — the whole point of the
        Settings 'Min Margin %' field the frontend exposes."""
        from src.pricing.models import MarginTarget
        from src.pricing.service import compute_suggestion

        product_id = uuid.uuid4()
        business_id = uuid.uuid4()
        lot = self._make_lot(product_id, units_remaining=10, unit_cost_ngn="15000")
        margin_target = MarginTarget(
            product_id=product_id,
            target_margin_pct=Decimal("40.00"),
            min_margin_pct=Decimal("50.00"),
            priority=1,
            set_by=uuid.uuid4(),
        )
        margin_target.id = uuid.uuid4()

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.all.return_value = [(lot, "USD")]
            elif call_count == 2:
                p = Product(
                    name="Widget", slug="widget", sku="SKU-1",
                    selling_price=Decimal("20000"), business_id=uuid.uuid4(),
                )
                p.id = product_id
                p.category_id = None
                p.category = None
                result.scalar_one_or_none.return_value = p
            else:
                result.scalars.return_value.all.return_value = [margin_target]
            return result

        db = _mock_db()
        db.execute = mock_execute

        with patch("src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock,
                   return_value=(Decimal("1700"), datetime.now(timezone.utc), True)):
            suggestion = await compute_suggestion(
                db, product_id, business_id=business_id
            )

        # target_margin (40%) alone would give 15000/0.60=25000, but the
        # 50% min_margin floor requires 15000/0.50=30000
        assert suggestion.suggested_price_ngn == Decimal("30000.000000")


# ---------------------------------------------------------------------------
# Tests for variant-scoped lot cost (task 171)
# ---------------------------------------------------------------------------


class TestComputeSuggestionVariantScoping:
    """compute_suggestion()'s weighted-average lot cost must not pool a
    sibling variant's lots — the same cross-variant bug task 165 fixed for
    fifo_deduct()/InventoryBatch and task 168 fixed for
    _deduct_lot_units()/OrderLineItem, on this third units_remaining
    consumer."""

    def _make_lot(self, product_id, units_remaining, unit_cost_ngn):
        from src.orders.models import OrderLineItem
        lot = MagicMock(spec=OrderLineItem)
        lot.product_id = product_id
        lot.units_remaining = Decimal(str(units_remaining))
        lot.unit_cost = Decimal("10")
        lot.unit_cost_ngn = Decimal(str(unit_cost_ngn))
        return lot

    def _make_variant(self, variant_id, product_id, price_override=None):
        from src.products.models import ProductVariant
        variant = MagicMock(spec=ProductVariant)
        variant.id = variant_id
        variant.product_id = product_id
        variant.price_override = price_override
        return variant

    @pytest.mark.asyncio
    async def test_without_variant_id_does_not_filter_by_variant_at_all(self):
        """Omitting variant_id (the default) must NOT narrow to untagged
        lots only — unlike fifo_deduct()/_deduct_lot_units(), a caller
        here (e.g. products-page.component.ts's "suggest price" button,
        which never passes variant_id) may simply not know/care about
        variant scoping and expects the pre-task-171 behaviour: pool
        across every lot for the product, tagged or not. Narrowing this
        to untagged-only would silently break price suggestions for every
        variant-tracked product for that caller."""
        from src.pricing.service import compute_suggestion

        product_id = uuid.uuid4()
        lot = self._make_lot(product_id, units_remaining=10, unit_cost_ngn="14000")

        db = _mock_db()
        call_count = 0
        captured_stmt = None

        async def mock_execute(stmt):
            nonlocal call_count, captured_stmt
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                captured_stmt = stmt
                result.all.return_value = [(lot, "USD")]
            else:
                p = MagicMock()
                p.selling_price = Decimal("20000")
                result.scalar_one_or_none.return_value = p
            return result

        db.execute = mock_execute

        with patch(
            "src.pricing.service.get_live_usdngn_rate",
            new_callable=AsyncMock,
            return_value=(Decimal("1700"), datetime.now(timezone.utc), True),
        ):
            await compute_suggestion(db, product_id, target_margin=Decimal("0.40"))

        compiled = str(
            captured_stmt.compile(compile_kwargs={"literal_binds": True})
        ).lower()
        assert "order_line_items.variant_id is null" not in compiled
        assert "order_line_items.variant_id =" not in compiled

    @pytest.mark.asyncio
    async def test_without_variant_id_still_succeeds_for_a_variant_tracked_product(
        self,
    ):
        """Regression check: a product whose ONLY lots are variant-tagged
        (no untagged fallback stock at all — the normal state for a
        variant-tracked product per recompute.py's own comment that
        "variant-tracked opening-stock imports never create [untagged
        lots]") must still produce a suggestion when the caller omits
        variant_id, exactly as it did before task 171. Filtering to
        untagged-only here would turn a working feature into a 422 for
        every variant-tracked product."""
        from src.pricing.service import compute_suggestion

        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        tagged_lot = self._make_lot(product_id, units_remaining=10, unit_cost_ngn="14000")
        tagged_lot.variant_id = variant_id  # no untagged lots exist at all

        db = _mock_db()
        db.execute = self._mock_execute_lots_then_product([(tagged_lot, "USD")])

        with patch(
            "src.pricing.service.get_live_usdngn_rate",
            new_callable=AsyncMock,
            return_value=(Decimal("1700"), datetime.now(timezone.utc), True),
        ):
            suggestion = await compute_suggestion(
                db, product_id, target_margin=Decimal("0.40")
            )

        assert suggestion.unit_cost_ngn == Decimal("14000")

    @pytest.mark.asyncio
    async def test_with_variant_id_matches_that_variant_or_untagged_lots(self):
        from src.pricing.service import compute_suggestion

        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        lot = self._make_lot(product_id, units_remaining=10, unit_cost_ngn="14000")
        variant = self._make_variant(variant_id, product_id)

        db = _mock_db()
        call_count = 0
        captured_stmt = None

        async def mock_execute(stmt):
            nonlocal call_count, captured_stmt
            call_count += 1
            result = MagicMock()
            if call_count == 1:  # variant-ownership lookup (validated first)
                result.scalar_one_or_none.return_value = variant
            elif call_count == 2:
                captured_stmt = stmt
                result.all.return_value = [(lot, "USD")]
            else:  # product lookup
                p = MagicMock()
                p.selling_price = Decimal("20000")
                result.scalar_one_or_none.return_value = p
            return result

        db.execute = mock_execute

        with patch(
            "src.pricing.service.get_live_usdngn_rate",
            new_callable=AsyncMock,
            return_value=(Decimal("1700"), datetime.now(timezone.utc), True),
        ):
            await compute_suggestion(
                db, product_id, target_margin=Decimal("0.40"), variant_id=variant_id
            )

        compiled = str(
            captured_stmt.compile(compile_kwargs={"literal_binds": True})
        ).lower()
        assert "order_line_items.variant_id is null" in compiled
        assert variant_id.hex in compiled.replace("-", "")
        assert (
            "order_line_items.variant_id = " in compiled
            or "order_line_items.variant_id=" in compiled
        )

    @pytest.mark.asyncio
    async def test_variant_scoped_suggestion_never_pools_sibling_variant_cost(self):
        """Deduction-math check: given only the lots a correctly-scoped
        query would return (a sibling variant's lot excluded, matching
        how the mock stands in for the real WHERE clause — see
        test_with_variant_id_matches_that_variant_or_untagged_lots above
        for the actual SQL-shape assertion), the weighted-average cost
        must come from exactly those lots."""
        from src.pricing.service import compute_suggestion

        product_id = uuid.uuid4()
        variant_a = uuid.uuid4()
        lot_a = self._make_lot(product_id, units_remaining=10, unit_cost_ngn="14000")
        variant = self._make_variant(variant_a, product_id)

        db = _mock_db()
        db.execute = self._mock_execute_lots_then_product(
            [(lot_a, "USD")], variant=variant, with_variant_lookup=True
        )

        with patch(
            "src.pricing.service.get_live_usdngn_rate",
            new_callable=AsyncMock,
            return_value=(Decimal("1700"), datetime.now(timezone.utc), True),
        ):
            suggestion = await compute_suggestion(
                db, product_id, target_margin=Decimal("0.40"), variant_id=variant_a
            )

        assert suggestion.unit_cost_ngn == Decimal("14000")

    @pytest.mark.asyncio
    async def test_raises_when_variant_does_not_belong_to_product(self):
        """A variant_id referencing a different product (or an inactive
        variant) must be rejected before a suggestion is computed or
        persisted — otherwise the weighted-average cost (drawn from
        *this* product's own lots, via variant_or_untagged_filter()'s
        untagged-lot fallback) would get silently mislabeled with a
        variant_id that isn't really eligible, corrupting suggestion
        history."""
        from src.pricing.exceptions import PricingSuggestionError
        from src.pricing.service import compute_suggestion

        product_id = uuid.uuid4()
        foreign_variant_id = uuid.uuid4()
        lot = self._make_lot(product_id, units_remaining=10, unit_cost_ngn="14000")

        db = _mock_db()
        # The variant-ownership lookup finds nothing for foreign_variant_id.
        db.execute = self._mock_execute_lots_then_product(
            [(lot, "USD")], variant=None, with_variant_lookup=True
        )

        with patch(
            "src.pricing.service.get_live_usdngn_rate",
            new_callable=AsyncMock,
            return_value=(Decimal("1700"), datetime.now(timezone.utc), True),
        ):
            with pytest.raises(PricingSuggestionError):
                await compute_suggestion(
                    db,
                    product_id,
                    target_margin=Decimal("0.40"),
                    variant_id=foreign_variant_id,
                )

    @pytest.mark.asyncio
    async def test_invalid_variant_id_rejected_before_lot_query_or_fx_fetch(self):
        """The variant-ownership check must run before the lot query and
        the live FX-rate fetch — get_live_usdngn_rate() can hit an
        external API and persist a new FXRate row on a cache miss, so an
        invalid/foreign variant_id shouldn't pay for either before being
        rejected."""
        from src.pricing.exceptions import PricingSuggestionError
        from src.pricing.service import compute_suggestion

        product_id = uuid.uuid4()
        foreign_variant_id = uuid.uuid4()

        db = _mock_db()
        lot_query_touched = False

        async def mock_execute(stmt):
            nonlocal lot_query_touched
            result = MagicMock()
            # The only db.execute() call before rejection must be the
            # variant-ownership lookup — anything selecting OrderLineItem
            # would mean the lot query ran first.
            if "order_line_items" in str(stmt).lower():
                lot_query_touched = True
            result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        with patch(
            "src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock
        ) as mock_fx:
            with pytest.raises(PricingSuggestionError):
                await compute_suggestion(
                    db,
                    product_id,
                    target_margin=Decimal("0.40"),
                    variant_id=foreign_variant_id,
                )

        assert lot_query_touched is False
        mock_fx.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_uses_variant_price_override_for_catalog_price(self):
        """current_catalog_price_ngn must reflect the requested variant's
        own price_override when set, not the product's base selling_price
        — mirrors how every other variant-aware price resolver in the
        codebase (products/service.py, sales/service.py, orders/service.py)
        already applies 'variant.price_override if set else
        product.selling_price'."""
        from src.pricing.service import compute_suggestion

        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        lot = self._make_lot(product_id, units_remaining=10, unit_cost_ngn="14000")
        variant = self._make_variant(
            variant_id, product_id, price_override=Decimal("25000")
        )

        db = _mock_db()
        db.execute = self._mock_execute_lots_then_product(
            [(lot, "USD")],
            catalog_price="20000",
            variant=variant,
            with_variant_lookup=True,
        )

        with patch(
            "src.pricing.service.get_live_usdngn_rate",
            new_callable=AsyncMock,
            return_value=(Decimal("1700"), datetime.now(timezone.utc), True),
        ):
            suggestion = await compute_suggestion(
                db, product_id, target_margin=Decimal("0.40"), variant_id=variant_id
            )

        assert suggestion.current_catalog_price_ngn == Decimal("25000")

    def _mock_execute_lots_then_product(
        self,
        lots_with_currency,
        catalog_price="20000",
        variant=None,
        with_variant_lookup=False,
    ):
        """If with_variant_lookup: call1=variant-ownership lookup (returns
        `variant`), call2=lots, call3=product — else call1=lots, call2=
        product. Matches compute_suggestion()'s query order: the
        variant-ownership check runs first, and only when variant_id is
        passed, before the lot query and live FX-rate fetch."""
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if with_variant_lookup and call_count == 1:
                result.scalar_one_or_none.return_value = variant
            elif (with_variant_lookup and call_count == 2) or (
                not with_variant_lookup and call_count == 1
            ):
                result.all.return_value = lots_with_currency
            else:
                p = MagicMock()
                p.selling_price = Decimal(str(catalog_price))
                result.scalar_one_or_none.return_value = p
            return result

        return mock_execute


class TestSuggestionHistoryVariantScoping:
    """get_suggestion_history() must not interleave a product's different
    variants' suggestions — otherwise browsing one variant's price/cost
    trend silently mixes in a sibling variant's numbers, undermining the
    whole point of scoping compute_suggestion() by variant (task 171)."""

    @pytest.mark.asyncio
    async def test_variant_id_filters_to_that_variant_only(self):
        from src.pricing.service import get_suggestion_history

        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()

        db = _mock_db()
        captured_stmt = None

        async def mock_execute(stmt):
            nonlocal captured_stmt
            captured_stmt = stmt
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute

        await get_suggestion_history(db, product_id, variant_id=variant_id)

        compiled = str(
            captured_stmt.compile(compile_kwargs={"literal_binds": True})
        ).lower()
        assert "price_suggestions.variant_id = " in compiled or (
            "price_suggestions.variant_id=" in compiled
        )
        assert variant_id.hex in compiled.replace("-", "")

    @pytest.mark.asyncio
    async def test_without_variant_id_does_not_filter_by_variant(self):
        """Omitting variant_id preserves prior behaviour: every suggestion
        for the product, regardless of which variant (or none) it was
        computed for."""
        from src.pricing.service import get_suggestion_history

        product_id = uuid.uuid4()

        db = _mock_db()
        captured_stmt = None

        async def mock_execute(stmt):
            nonlocal captured_stmt
            captured_stmt = stmt
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute

        await get_suggestion_history(db, product_id)

        compiled = str(
            captured_stmt.compile(compile_kwargs={"literal_binds": True})
        ).lower()
        # The SELECT column list naturally mentions variant_id (it's a
        # column on the model) — only the WHERE-clause comparison must be
        # absent when variant_id isn't passed.
        assert "price_suggestions.variant_id =" not in compiled
        assert "price_suggestions.variant_id=" not in compiled

    @pytest.mark.asyncio
    async def test_raises_when_variant_id_does_not_belong_to_product(self):
        """A mismatched product_id/variant_id pair must raise, not
        silently return an empty list — an empty result is otherwise
        indistinguishable from 'this variant has no suggestions yet',
        masking a client-side bug that passed the wrong pair."""
        from src.pricing.exceptions import PricingSuggestionError
        from src.pricing.service import get_suggestion_history

        product_id = uuid.uuid4()
        foreign_variant_id = uuid.uuid4()

        db = _mock_db()

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None  # ownership lookup finds nothing
            return result

        db.execute = mock_execute

        with pytest.raises(PricingSuggestionError):
            await get_suggestion_history(db, product_id, variant_id=foreign_variant_id)

    @pytest.mark.asyncio
    async def test_deactivated_variants_history_stays_visible(self):
        """Unlike compute_suggestion() (which rejects an inactive variant
        before computing a *new* suggestion), reading a deactivated
        variant's *past* suggestion history must still succeed — this is
        a read of history, not a request against the variant's current
        lot stock, so an is_active=False variant is still a valid
        ownership match here."""
        from src.pricing.service import get_suggestion_history

        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()

        db = _mock_db()

        async def mock_execute(stmt):
            result = MagicMock()
            # Ownership lookup finds the (inactive) variant just fine —
            # is_active is never part of this query's WHERE clause.
            result.scalar_one_or_none.return_value = MagicMock(
                id=variant_id, product_id=product_id, is_active=False
            )
            result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute

        result = await get_suggestion_history(db, product_id, variant_id=variant_id)

        assert result == []


# ---------------------------------------------------------------------------
# Tests for category-aware price suggestion margin (Task #80)
# ---------------------------------------------------------------------------


class TestCategoryAwarePriceSuggestion:
    """compute_suggestion resolves target_margin from product's category hierarchy."""

    def _make_lot(self, product_id, units_remaining, unit_cost_ngn="10000"):
        from src.orders.models import OrderLineItem
        lot = MagicMock(spec=OrderLineItem)
        lot.product_id = product_id
        lot.units_remaining = Decimal(str(units_remaining))
        lot.unit_cost = Decimal("10")
        lot.unit_cost_ngn = Decimal(str(unit_cost_ngn))
        return lot

    def _make_product_mock(self, cat_margin=None, parent_margin=None):
        """Build a mock Product with category and optional parent populated."""
        parent = None
        if parent_margin is not None:
            parent = MagicMock()
            parent.default_margin_pct = Decimal(str(parent_margin))

        cat = MagicMock()
        cat.default_margin_pct = Decimal(str(cat_margin)) if cat_margin is not None else None
        cat.parent = parent

        product = MagicMock()
        product.selling_price = Decimal("20000")
        product.category = cat
        return product

    def _make_db(self, lots_with_currency, product):
        """Two-query mock: call 1 → lots, call 2 → product with category."""
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.all.return_value = lots_with_currency
            else:
                result.scalar_one_or_none.return_value = product
            return result

        db = _mock_db()
        db.execute = mock_execute
        return db

    @pytest.mark.asyncio
    async def test_compute_suggestion_uses_category_margin(self):
        """When no explicit margin is given, the category default (0.35) is used."""
        from src.pricing.service import compute_suggestion

        product_id = uuid.uuid4()
        lot = self._make_lot(product_id, units_remaining=10, unit_cost_ngn="10000")
        product = self._make_product_mock(cat_margin="0.35")
        db = self._make_db([(lot, "USD")], product)

        with patch("src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock,
                   return_value=(Decimal("1700"), datetime.now(timezone.utc), True)):
            suggestion = await compute_suggestion(db, product_id)

        expected = Decimal("10000") / Decimal("0.65")
        assert abs(suggestion.suggested_price_ngn - expected) < Decimal("1")
        assert suggestion.target_margin_pct == Decimal("0.35")

    @pytest.mark.asyncio
    async def test_compute_suggestion_inherits_parent_margin(self):
        """Sub-category with no margin inherits parent's default_margin_pct (0.30)."""
        from src.pricing.service import compute_suggestion

        product_id = uuid.uuid4()
        lot = self._make_lot(product_id, units_remaining=10, unit_cost_ngn="10000")
        product = self._make_product_mock(cat_margin=None, parent_margin="0.30")
        db = self._make_db([(lot, "USD")], product)

        with patch("src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock,
                   return_value=(Decimal("1700"), datetime.now(timezone.utc), True)):
            suggestion = await compute_suggestion(db, product_id)

        expected = Decimal("10000") / Decimal("0.70")
        assert abs(suggestion.suggested_price_ngn - expected) < Decimal("1")
        assert suggestion.target_margin_pct == Decimal("0.30")

    @pytest.mark.asyncio
    async def test_compute_suggestion_explicit_overrides_category(self):
        """Explicit target_margin=0.50 wins over category default (0.35)."""
        from src.pricing.service import compute_suggestion

        product_id = uuid.uuid4()
        lot = self._make_lot(product_id, units_remaining=10, unit_cost_ngn="10000")
        product = self._make_product_mock(cat_margin="0.35")
        db = self._make_db([(lot, "USD")], product)

        with patch("src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock,
                   return_value=(Decimal("1700"), datetime.now(timezone.utc), True)):
            suggestion = await compute_suggestion(db, product_id, target_margin=Decimal("0.50"))

        expected = Decimal("10000") / Decimal("0.50")
        assert abs(suggestion.suggested_price_ngn - expected) < Decimal("1")
        assert suggestion.target_margin_pct == Decimal("0.50")

    @pytest.mark.asyncio
    async def test_compute_suggestion_falls_back_to_default(self):
        """No category margin and no parent: falls back to system default 40%."""
        from src.pricing.service import compute_suggestion

        product_id = uuid.uuid4()
        lot = self._make_lot(product_id, units_remaining=10, unit_cost_ngn="10000")
        product = self._make_product_mock(cat_margin=None, parent_margin=None)
        db = self._make_db([(lot, "USD")], product)

        with patch("src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock,
                   return_value=(Decimal("1700"), datetime.now(timezone.utc), True)):
            suggestion = await compute_suggestion(db, product_id)

        expected = Decimal("10000") / Decimal("0.60")
        assert abs(suggestion.suggested_price_ngn - expected) < Decimal("1")
        assert suggestion.target_margin_pct == Decimal("0.40")


# ---------------------------------------------------------------------------
# Portfolio Margin API response shape
# ---------------------------------------------------------------------------


class TestPortfolioMarginResponseShape:
    """Verify that the portfolio-margin endpoint returns the fields the frontend expects."""

    @pytest.fixture(autouse=True)
    def _setup_client(self):
        from src.main import app

        self.app = app
        self._original_overrides = app.dependency_overrides.copy()
        yield
        app.dependency_overrides = self._original_overrides

    def _override_auth(self):
        from src.auth.dependencies import get_current_active_user, get_current_business_id

        u = _make_user(business_id=BUSINESS_ID)

        async def _fake_auth():
            return u

        async def _fake_business_id():
            return BUSINESS_ID

        self.app.dependency_overrides[get_current_active_user] = _fake_auth
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id

    def test_portfolio_margin_returns_margin_gap_field(self):
        """Response must include margin_gap (not gap) — matches frontend mapping."""
        from unittest.mock import MagicMock, AsyncMock

        self._override_auth()

        from src.core.database import get_db

        async def _fake_db():
            # Return empty products (no sales in last 30d)
            result_mock = MagicMock()
            result_mock.all.return_value = []
            db = AsyncMock()
            db.execute = AsyncMock(return_value=result_mock)
            db.flush = AsyncMock()
            yield db

        self.app.dependency_overrides[get_db] = _fake_db

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/pricing/portfolio-margin")

        assert resp.status_code == 200
        body = resp.json()
        # These are the exact keys the frontend service maps from:
        assert "blended_margin" in body
        assert "target_margin" in body
        assert "margin_gap" in body, "Frontend maps 'margin_gap' → 'gap'; field must be present"
        assert "products" in body

    def test_portfolio_margin_product_shape(self):
        """Each product entry must have margin_pct and unit_cost (not current_margin/cost_price).
        Now uses two queries: first for sales data, second for all active products."""
        from unittest.mock import MagicMock, AsyncMock
        from decimal import Decimal

        self._override_auth()
        from src.core.database import get_db

        async def _fake_db():
            pid = uuid.uuid4()

            # First execute: sales aggregation query → (product_id, qty, revenue)
            sales_result = MagicMock()
            sales_result.all.return_value = [(pid, 10, Decimal("15000"))]

            # Second execute: all active products → (id, name, unit_cost, selling_price)
            products_result = MagicMock()
            products_result.all.return_value = [
                (pid, "Widget", Decimal("1000"), Decimal("1500"))
            ]

            db = AsyncMock()
            db.execute = AsyncMock(side_effect=[sales_result, products_result])
            db.flush = AsyncMock()
            yield db

        self.app.dependency_overrides[get_db] = _fake_db

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/pricing/portfolio-margin")

        assert resp.status_code == 200
        products = resp.json()["products"]
        assert len(products) == 1
        p = products[0]
        assert "margin_pct" in p, "Frontend maps margin_pct → current_margin"
        assert "unit_cost" in p, "Frontend maps unit_cost → cost_price"
        assert "selling_price" in p
        assert "current_margin" not in p
        assert "cost_price" not in p


# ---------------------------------------------------------------------------
# calculate_portfolio_margin — all-products inclusion
# ---------------------------------------------------------------------------


class TestCalculatePortfolioMarginAllProducts:
    """Verify that all active products appear in the per-product breakdown,
    regardless of whether they had sales in the last 30 days."""

    def _make_db(self, sales_rows, product_rows):
        """Return a mock db where the first execute returns sales_rows
        and the second returns product_rows."""
        sales_result = MagicMock()
        sales_result.all.return_value = sales_rows

        products_result = MagicMock()
        products_result.all.return_value = product_rows

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[sales_result, products_result])
        return db

    @pytest.mark.asyncio
    async def test_product_without_sales_appears_with_theoretical_margin(self):
        """A product with no 30-day sales must still appear using cost vs price margin."""
        from src.pricing.service import calculate_portfolio_margin

        pid = uuid.uuid4()
        # No sales rows
        db = self._make_db(
            sales_rows=[],
            product_rows=[(pid, "Widget", Decimal("1000"), Decimal("1500"))],
        )

        result = await calculate_portfolio_margin(db)

        assert len(result["products"]) == 1
        p = result["products"][0]
        assert p["product_name"] == "Widget"
        # Theoretical margin: (1500 - 1000) / 1500 * 100 = 33.33%
        assert abs(p["margin_pct"] - 33.33) < 0.1
        assert p["revenue_30d"] == Decimal("0")
        assert p["quantity_30d"] == 0

    @pytest.mark.asyncio
    async def test_blended_margin_only_counts_products_with_sales(self):
        """Blended portfolio margin is revenue-weighted; no-sale products don't shift it."""
        from src.pricing.service import calculate_portfolio_margin

        pid1 = uuid.uuid4()
        pid2 = uuid.uuid4()

        # Only pid1 has sales: 10 units @ ₦1500 = ₦15 000 revenue, COGS = 10×₦1000 = ₦10 000
        db = self._make_db(
            sales_rows=[(pid1, 10, Decimal("15000"))],
            product_rows=[
                (pid1, "Product A", Decimal("1000"), Decimal("1500")),
                (pid2, "Product B", Decimal("500"), Decimal("800")),
            ],
        )

        result = await calculate_portfolio_margin(db)

        assert len(result["products"]) == 2

        # Blended margin = (15000 - 10000) / 15000 × 100 = 33.33 % (only from Product A)
        assert abs(float(result["blended_margin"]) - 33.33) < 0.1

        # Product B: theoretical margin = (800 - 500) / 800 × 100 = 37.5 %
        product_b = next(p for p in result["products"] if p["product_name"] == "Product B")
        assert abs(product_b["margin_pct"] - 37.5) < 0.1
        assert product_b["revenue_30d"] == Decimal("0")

    @pytest.mark.asyncio
    async def test_product_with_sales_uses_actual_revenue_margin(self):
        """Products with sales use (revenue − COGS) / revenue, not theoretical price margin."""
        from src.pricing.service import calculate_portfolio_margin

        pid = uuid.uuid4()
        # Sold at ₦1500 avg (< current selling_price ₦2000) — actual margin ≠ theoretical
        db = self._make_db(
            sales_rows=[(pid, 10, Decimal("15000"))],
            product_rows=[(pid, "Widget", Decimal("1200"), Decimal("2000"))],
        )

        result = await calculate_portfolio_margin(db)

        p = result["products"][0]
        # Actual: (15000 − 12000) / 15000 × 100 = 20 %, not theoretical (2000−1200)/2000 = 40 %
        assert abs(p["margin_pct"] - 20.0) < 0.1
        assert p["revenue_30d"] == Decimal("15000")
        assert p["quantity_30d"] == 10

    @pytest.mark.asyncio
    async def test_zero_selling_price_product_shows_zero_margin(self):
        """Products with selling_price = 0 must not raise a ZeroDivisionError."""
        from src.pricing.service import calculate_portfolio_margin

        pid = uuid.uuid4()
        db = self._make_db(
            sales_rows=[],
            product_rows=[(pid, "Free Item", Decimal("0"), Decimal("0"))],
        )

        result = await calculate_portfolio_margin(db)

        assert result["products"][0]["margin_pct"] == 0.0


# ---------------------------------------------------------------------------
# Sensitivity Calc API
# ---------------------------------------------------------------------------


class TestSensitivityCalcEndpoint:
    @pytest.fixture(autouse=True)
    def _setup_client(self):
        from src.main import app

        self.app = app
        self._original_overrides = app.dependency_overrides.copy()
        yield
        app.dependency_overrides = self._original_overrides

    def _override_auth(self):
        from src.auth.dependencies import get_current_active_user

        u = _make_user()

        async def _fake_auth():
            return u

        self.app.dependency_overrides[get_current_active_user] = _fake_auth

    def test_sensitivity_calc_stateless(self):
        """Stateless calc with explicit unit_cost_usd returns expected margin."""
        from src.core.database import get_db
        from unittest.mock import AsyncMock, MagicMock

        self._override_auth()

        async def _fake_db():
            db = AsyncMock()
            db.execute = AsyncMock(return_value=MagicMock())
            db.flush = AsyncMock()
            yield db

        self.app.dependency_overrides[get_db] = _fake_db

        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/pricing/sensitivity-calc",
                json={
                    "selling_price_override": 5000,
                    "fx_rate_override": 1500,
                    "quantity": 10,
                    "unit_cost_usd": 2,  # $2 * 1500 = ₦3000 landed cost
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "margin_pct" in body
        assert "landed_cost_ngn" in body
        assert "gross_profit" in body
        # margin = (5000 - 3000) / 5000 * 100 = 40%
        assert float(body["margin_pct"]) == pytest.approx(40.0, abs=0.1)

    def test_sensitivity_calc_requires_cost_source(self):
        """Without product_id or unit_cost_usd the endpoint returns 400."""
        from src.core.database import get_db
        from unittest.mock import AsyncMock, MagicMock

        self._override_auth()

        async def _fake_db():
            db = AsyncMock()
            db.execute = AsyncMock(return_value=MagicMock())
            yield db

        self.app.dependency_overrides[get_db] = _fake_db

        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/pricing/sensitivity-calc",
                json={
                    "selling_price_override": 5000,
                    "fx_rate_override": 1500,
                    "quantity": 10,
                    # neither product_id nor unit_cost_usd
                },
            )

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Task #165 — fx_rate_stale + fx_rate_source in SellingPriceSuggestionResponse
# ---------------------------------------------------------------------------


class TestSellingPriceSuggestionStaleFlag:
    """SellingPriceSuggestionResponse must expose fx_rate_stale and fx_rate_source."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from src.main import app

        self.app = app
        self._orig = app.dependency_overrides.copy()
        yield
        app.dependency_overrides = self._orig

    def _override_auth(self):
        from src.auth.dependencies import get_current_active_user

        async def _auth():
            return _make_user()

        self.app.dependency_overrides[get_current_active_user] = _auth

    def test_ngn_currency_is_never_stale(self):
        """NGN product costs need no FX conversion — stale flag must be False."""
        from src.core.database import get_db
        from unittest.mock import AsyncMock

        self._override_auth()

        async def _fake_db():
            db = AsyncMock()
            yield db

        self.app.dependency_overrides[get_db] = _fake_db

        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/pricing/selling-price-suggestion",
                json={
                    "unit_cost_override": 1000,
                    "currency": "NGN",
                    "min_margin_pct": 35,
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "fx_rate_stale" in body
        assert body["fx_rate_stale"] is False
        assert "fx_rate_source" in body

    def test_fx_rate_override_is_never_stale(self):
        """Explicit fx_rate_override bypasses the FX service — stale must be False."""
        from src.core.database import get_db
        from unittest.mock import AsyncMock

        self._override_auth()

        async def _fake_db():
            db = AsyncMock()
            yield db

        self.app.dependency_overrides[get_db] = _fake_db

        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/pricing/selling-price-suggestion",
                json={
                    "unit_cost_override": 10,
                    "currency": "USD",
                    "fx_rate_override": 1550,
                    "min_margin_pct": 35,
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["fx_rate_stale"] is False
        assert body["fx_rate_source"] == "override"

    def test_stale_usd_rate_sets_stale_flag(self):
        """When the cached FX rate is older than FX_CACHE_TTL_HOURS, stale must be True."""
        from datetime import datetime, timedelta, timezone
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.core.config import settings

        self._override_auth()

        from src.core.database import get_db

        async def _fake_db():
            db = AsyncMock()
            yield db

        self.app.dependency_overrides[get_db] = _fake_db

        # Timestamp older than the cache TTL → stale
        stale_ts = datetime.now(timezone.utc) - timedelta(
            hours=settings.FX_CACHE_TTL_HOURS + 1
        )
        mock_rate = MagicMock()
        mock_rate.rate = Decimal("1600")
        mock_rate.timestamp = stale_ts
        mock_rate.source.value = "api_provider"

        with patch(
            "src.fx.service.get_current_rate",
            new_callable=AsyncMock,
            return_value=mock_rate,
        ):
            with TestClient(self.app) as client:
                resp = client.post(
                    "/api/v1/pricing/selling-price-suggestion",
                    json={
                        "unit_cost_override": 10,
                        "currency": "USD",
                        "min_margin_pct": 35,
                    },
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["fx_rate_stale"] is True
        assert body["fx_rate_source"] == "cached"


# ---------------------------------------------------------------------------
# Task #172 — asyncio.wait_for timeout on SciPy minimize()
# ---------------------------------------------------------------------------


class TestOptimizationTimeout:
    """SciPy minimize() must be wrapped in asyncio.wait_for with a 30s timeout."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from src.main import app

        self.app = app
        self._orig = app.dependency_overrides.copy()
        yield
        app.dependency_overrides = self._orig

    def _override_auth(self):
        from src.auth.dependencies import get_current_active_user, get_current_business_id

        async def _auth():
            return _make_user()

        self.app.dependency_overrides[get_current_active_user] = _auth
        self.app.dependency_overrides[get_current_business_id] = lambda: uuid.uuid4()

    def test_timeout_returns_504(self):
        """When SciPy minimize() times out the endpoint must return HTTP 504."""
        from src.core.database import get_db
        from unittest.mock import AsyncMock, patch

        self._override_auth()

        async def _fake_db():
            db = AsyncMock()
            yield db

        self.app.dependency_overrides[get_db] = _fake_db

        from src.fx.exceptions import ForecastTimeoutError

        with patch(
            "src.pricing.router.generate_recommendations",
            new_callable=AsyncMock,
            side_effect=ForecastTimeoutError("SciPy price optimization", 30.0),
        ):
            with TestClient(self.app) as client:
                resp = client.post(
                    "/api/v1/pricing/recommendations/generate",
                    json={"target_margin": "35.00"},
                )

        assert resp.status_code == 504

    def test_normal_completion_returns_201(self):
        """When optimization completes within timeout, endpoint returns 201."""
        from src.core.database import get_db
        from unittest.mock import AsyncMock, patch

        self._override_auth()

        async def _fake_db():
            db = AsyncMock()
            yield db

        self.app.dependency_overrides[get_db] = _fake_db

        with patch(
            "src.pricing.router.generate_recommendations",
            new_callable=AsyncMock,
            return_value=[],
        ):
            with TestClient(self.app) as client:
                resp = client.post(
                    "/api/v1/pricing/recommendations/generate",
                    json={"target_margin": "35.00"},
                )

        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_service_raises_forecast_timeout_when_wait_for_times_out(self):
        """Service must catch asyncio.TimeoutError from wait_for and raise ForecastTimeoutError.

        Patches asyncio.wait_for directly so this test breaks if the guard is removed
        from the service, regardless of what the router does.
        """
        from decimal import Decimal
        from unittest.mock import AsyncMock, patch, MagicMock
        from src.fx.exceptions import ForecastTimeoutError
        from src.pricing.service import generate_recommendations

        db = AsyncMock()

        # No products below target margin → optimization never runs; patch
        # calculate_portfolio_margin to return a product below target so the
        # optimizer branch is entered.
        mock_portfolio = {
            "blended_margin": Decimal("20"),
            "products": [
                {
                    "product_id": str(uuid.uuid4()),
                    "product_name": "Widget",
                    "unit_cost": Decimal("50"),
                    "selling_price": Decimal("60"),
                    "margin_pct": 16.7,
                    "quantity_30d": 30,
                }
            ],
        }

        with patch(
            "src.pricing.service.calculate_portfolio_margin",
            new_callable=AsyncMock,
            return_value=mock_portfolio,
        ), patch(
            "src.pricing.service._get_elasticity_coefficient",
            new_callable=AsyncMock,
            return_value=Decimal("-1.5"),
        ), patch(
            "src.pricing.service.asyncio.wait_for",
            side_effect=asyncio.TimeoutError(),
        ):
            with pytest.raises(ForecastTimeoutError):
                await generate_recommendations(
                    db, business_id=uuid.uuid4(), target_margin=Decimal("35")
                )


class TestSuggestPricesForOrder:
    """suggest_prices_for_order() — per-line-item selling-price suggestions
    costed directly off the order's own line items (works at any order
    status, unlike the lot-based compute_suggestion()), using the LIVE
    current FX rate and each product's category target margin."""

    def _make_order(self, currency="USD", shipping_cost="0", clearing_cost="0", line_items=None):
        from src.orders.models import PurchaseOrder

        order = PurchaseOrder(
            order_number="PO-2026-00001",
            supplier_name="Test Supplier",
            status="DELIVERED",
            total_amount=Decimal("1000"),
            currency=currency,
            shipping_cost=Decimal(shipping_cost),
            clearing_cost=Decimal(clearing_cost),
            created_by=uuid.uuid4(),
        )
        order.id = uuid.uuid4()
        order.line_items = line_items or []
        return order

    def _make_line_item(self, product_id, quantity=1, unit_cost="10", unit_cost_ngn=None):
        from src.orders.models import OrderLineItem

        li = OrderLineItem(
            order_id=uuid.uuid4(),
            product_id=product_id,
            quantity=quantity,
            unit_cost=Decimal(unit_cost),
            unit_cost_ngn=Decimal(unit_cost_ngn) if unit_cost_ngn is not None else None,
            line_total=Decimal(unit_cost) * quantity,
        )
        li.id = uuid.uuid4()
        return li

    def _make_product(self, product_id, name="Widget", selling_price="20000", default_margin_pct=None):
        product = Product(
            name=name,
            slug=name.lower(),
            sku=f"SKU-{name}",
            selling_price=Decimal(selling_price),
            business_id=uuid.uuid4(),
        )
        product.id = product_id
        if default_margin_pct is not None:
            category = ProductCategory(name="Cat", business_id=uuid.uuid4())
            category.id = uuid.uuid4()
            category.default_margin_pct = Decimal(default_margin_pct)
            category.parent = None
            category.parent_id = None
            product.category = category
            product.category_id = category.id
        else:
            product.category = None
            product.category_id = None
        return product

    def _mock_execute_products(self, products):
        async def mock_execute(stmt):
            result = MagicMock()
            result.scalars.return_value.all.return_value = products
            return result

        return mock_execute

    def _mock_execute_products_then_targets(self, products, margin_targets):
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.scalars.return_value.all.return_value = (
                products if call_count == 1 else margin_targets
            )
            return result

        return mock_execute

    @pytest.mark.asyncio
    async def test_usd_order_converts_via_live_fx_rate(self):
        from src.pricing.service import suggest_prices_for_order

        product_id = uuid.uuid4()
        li = self._make_line_item(product_id, quantity=10, unit_cost="10")
        order = self._make_order(currency="USD", line_items=[li])
        product = self._make_product(product_id, default_margin_pct="0.40")

        db = _mock_db()
        db.execute = self._mock_execute_products([product])

        with patch("src.pricing.service.get_order", new_callable=AsyncMock, return_value=order), \
             patch("src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock,
                   return_value=(Decimal("1500"), datetime.now(timezone.utc), True)):
            result = await suggest_prices_for_order(db, order.id)

        # cost_ngn = 10 * 1500 = 15000; suggested = 15000 / 0.60 = 25000
        assert result["fx_rate_used"] == Decimal("1500")
        item = result["items"][0]
        assert item["unit_cost_ngn"] == Decimal("15000.000000")
        assert item["suggested_price_ngn"] == Decimal("15000") / Decimal("0.60")
        assert item["target_margin_pct"] == Decimal("0.40")
        assert item["current_price_ngn"] == Decimal("20000")

    @pytest.mark.asyncio
    async def test_ngn_order_uses_unit_cost_directly_no_fx_conversion(self):
        from src.pricing.service import suggest_prices_for_order

        product_id = uuid.uuid4()
        li = self._make_line_item(product_id, quantity=5, unit_cost="14000")
        order = self._make_order(currency="NGN", line_items=[li])
        product = self._make_product(product_id, default_margin_pct="0.40")

        db = _mock_db()
        db.execute = self._mock_execute_products([product])

        with patch("src.pricing.service.get_order", new_callable=AsyncMock, return_value=order), \
             patch("src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock,
                   return_value=(Decimal("1500"), datetime.now(timezone.utc), True)):
            result = await suggest_prices_for_order(db, order.id)

        item = result["items"][0]
        assert item["unit_cost_ngn"] == Decimal("14000.000000")

    @pytest.mark.asyncio
    async def test_shipping_and_clearing_allocated_per_unit(self):
        from src.pricing.service import suggest_prices_for_order

        product_id = uuid.uuid4()
        li = self._make_line_item(product_id, quantity=10, unit_cost="10")
        order = self._make_order(
            currency="USD", shipping_cost="500", clearing_cost="500", line_items=[li]
        )
        product = self._make_product(product_id, default_margin_pct="0.40")

        db = _mock_db()
        db.execute = self._mock_execute_products([product])

        with patch("src.pricing.service.get_order", new_callable=AsyncMock, return_value=order), \
             patch("src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock,
                   return_value=(Decimal("1500"), datetime.now(timezone.utc), True)):
            result = await suggest_prices_for_order(db, order.id)

        # logistics_per_unit = (500+500)/10 = 100; landed = 10*1500 + 100 = 15100
        item = result["items"][0]
        assert item["unit_cost_ngn"] == Decimal("15100.000000")

    @pytest.mark.asyncio
    async def test_no_category_falls_back_to_default_margin(self):
        from src.pricing.service import suggest_prices_for_order

        product_id = uuid.uuid4()
        li = self._make_line_item(product_id, quantity=1, unit_cost="10")
        order = self._make_order(currency="USD", line_items=[li])
        product = self._make_product(product_id, default_margin_pct=None)

        db = _mock_db()
        db.execute = self._mock_execute_products([product])

        with patch("src.pricing.service.get_order", new_callable=AsyncMock, return_value=order), \
             patch("src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock,
                   return_value=(Decimal("1500"), datetime.now(timezone.utc), True)):
            result = await suggest_prices_for_order(db, order.id)

        assert result["items"][0]["target_margin_pct"] == Decimal("0.40")

    @pytest.mark.asyncio
    async def test_order_not_found_propagates(self):
        from src.orders.exceptions import OrderNotFoundError
        from src.pricing.service import suggest_prices_for_order

        db = _mock_db()
        order_id = uuid.uuid4()

        with patch("src.pricing.service.get_order", new_callable=AsyncMock,
                   side_effect=OrderNotFoundError(order_id)):
            with pytest.raises(OrderNotFoundError):
                await suggest_prices_for_order(db, order_id)

    @pytest.mark.asyncio
    async def test_margin_target_overrides_category_default(self):
        """A Settings-configured MarginTarget for the product's category
        must be used instead of ProductCategory.default_margin_pct, when
        business_id is provided."""
        from src.pricing.service import suggest_prices_for_order

        product_id = uuid.uuid4()
        li = self._make_line_item(product_id, quantity=1, unit_cost="10")
        order = self._make_order(currency="USD", line_items=[li])
        product = self._make_product(product_id, default_margin_pct="0.50")
        margin_target = MarginTarget(
            category_id=product.category_id,
            target_margin_pct=Decimal("25.00"),
            min_margin_pct=Decimal("10.00"),
            priority=1,
            set_by=uuid.uuid4(),
        )
        margin_target.id = uuid.uuid4()

        db = _mock_db()
        db.execute = self._mock_execute_products_then_targets([product], [margin_target])
        business_id = uuid.uuid4()

        with patch("src.pricing.service.get_order", new_callable=AsyncMock, return_value=order), \
             patch("src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock,
                   return_value=(Decimal("1500"), datetime.now(timezone.utc), True)):
            result = await suggest_prices_for_order(db, order.id, business_id=business_id)

        # MarginTarget's 25% (0.25), not the category's default 50% (0.50)
        assert result["items"][0]["target_margin_pct"] == Decimal("0.25")

    @pytest.mark.asyncio
    async def test_no_business_id_skips_margin_target_lookup(self):
        """business_id=None (e.g. a caller that doesn't have tenant
        context) must not attempt a MarginTarget query at all — falls
        through to the category default cleanly."""
        from src.pricing.service import suggest_prices_for_order

        product_id = uuid.uuid4()
        li = self._make_line_item(product_id, quantity=1, unit_cost="10")
        order = self._make_order(currency="USD", line_items=[li])
        product = self._make_product(product_id, default_margin_pct="0.50")

        db = _mock_db()
        db.execute = self._mock_execute_products([product])

        with patch("src.pricing.service.get_order", new_callable=AsyncMock, return_value=order), \
             patch("src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock,
                   return_value=(Decimal("1500"), datetime.now(timezone.utc), True)):
            result = await suggest_prices_for_order(db, order.id, business_id=None)

        assert result["items"][0]["target_margin_pct"] == Decimal("0.50")

    @pytest.mark.asyncio
    async def test_min_margin_pct_floors_the_suggested_price(self):
        """Same min_margin_pct floor as compute_suggestion(), applied per
        line item here."""
        from src.pricing.service import suggest_prices_for_order

        product_id = uuid.uuid4()
        li = self._make_line_item(product_id, quantity=10, unit_cost="10")
        order = self._make_order(currency="USD", line_items=[li])
        product = self._make_product(product_id, default_margin_pct="0.40")
        margin_target = MarginTarget(
            product_id=product_id,
            target_margin_pct=Decimal("40.00"),
            min_margin_pct=Decimal("50.00"),
            priority=1,
            set_by=uuid.uuid4(),
        )
        margin_target.id = uuid.uuid4()

        db = _mock_db()
        db.execute = self._mock_execute_products_then_targets([product], [margin_target])
        business_id = uuid.uuid4()

        with patch("src.pricing.service.get_order", new_callable=AsyncMock, return_value=order), \
             patch("src.pricing.service.get_live_usdngn_rate", new_callable=AsyncMock,
                   return_value=(Decimal("1500"), datetime.now(timezone.utc), True)):
            result = await suggest_prices_for_order(db, order.id, business_id=business_id)

        # cost_ngn = 10 * 1500 = 15000; 40% target would give 25000, but
        # the 50% min_margin floor requires 15000/0.50=30000
        assert result["items"][0]["suggested_price_ngn"] == Decimal("30000.000000")
