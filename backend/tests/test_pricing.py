"""Tests for pricing domain: demand forecast, margin optimization, recommendations."""

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
        result = await get_recommendations(db)
        assert result == []

    @pytest.mark.asyncio
    async def test_apply_recommendation_not_found(self):
        from src.pricing.service import apply_recommendation

        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(RecommendationNotFoundError):
            await apply_recommendation(db, uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_apply_recommendation_expired(self):
        from src.pricing.service import apply_recommendation

        rec = _make_recommendation(
            created_at=datetime.now(timezone.utc) - timedelta(days=60)
        )
        db = _mock_db_with_execute(scalar_result=rec)
        with pytest.raises(RecommendationExpiredError):
            await apply_recommendation(db, rec.id, uuid.uuid4())

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

        result = await apply_recommendation(db, rec.id, uuid.uuid4())
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
        result = await dismiss_recommendation(db, rec.id)
        assert result.status == RecommendationStatus.REJECTED

    @pytest.mark.asyncio
    async def test_dismiss_recommendation_not_found(self):
        from src.pricing.service import dismiss_recommendation

        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(RecommendationNotFoundError):
            await dismiss_recommendation(db, uuid.uuid4())


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
        result = await set_margin_target(db, data, uuid.uuid4())
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
        result = await get_margin_targets(db)
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

    def test_recommendations_empty(self):
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
