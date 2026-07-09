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
