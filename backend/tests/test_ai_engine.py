"""Tests for the AI Engine domain."""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.ai_engine.exceptions import (
    RecommendationAlreadyProcessedError,
    RecommendationExpiredError,
    RecommendationNotFoundError,
    ReorderSuggestionNotFoundError,
    USDStrategyConfigNotFoundError,
)
from src.ai_engine.models import (
    AIRecommendation,
    ActionType,
    RecommendationCategory,
    RecommendationPriority,
    RecommendationStatus,
    ReorderSuggestion,
    ReorderStatus,
    USDStrategyConfig,
)
from src.ai_engine.service import (
    _assign_priority_level,
    _calculate_priority_score,
    _calculate_urgency,
    apply_recommendation,
    approve_reorder,
    dismiss_recommendation,
    generate_usd_accumulation_schedule,
    get_impact_summary,
    get_recommendation,
    get_recommendation_history,
    get_recommendations,
    get_reorder_suggestion,
    get_reorder_suggestions,
    get_usd_strategy_config,
)
from src.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc)


def _make_recommendation(**overrides) -> AIRecommendation:
    defaults = dict(
        id=uuid.uuid4(),
        category=RecommendationCategory.PRICING,
        title="Test recommendation",
        description="Test description",
        priority=RecommendationPriority.MEDIUM,
        confidence=Decimal("75.00"),
        expected_impact={"metric": "test", "estimated_revenue_impact": "1000"},
        action_type=ActionType.PRICE_CHANGE,
        action_payload={"product_id": str(uuid.uuid4()), "suggested_price": "1500.00"},
        reference_id=uuid.uuid4(),
        reference_type="product",
        status=RecommendationStatus.PENDING,
        dismissed_reason=None,
        accepted_by=None,
        accepted_at=None,
        measured_outcome=None,
        created_at=NOW,
        expires_at=NOW + timedelta(days=30),
    )
    defaults.update(overrides)
    rec = MagicMock(spec=AIRecommendation)
    for k, v in defaults.items():
        setattr(rec, k, v)
    return rec


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


_SENTINEL = object()


def _mock_db_with_execute(return_val=_SENTINEL, scalar_val=None, scalars_list=None):
    db = _mock_db()
    mock_result = MagicMock()
    if return_val is not _SENTINEL:
        mock_result.scalar_one_or_none.return_value = return_val
    if scalar_val is not None:
        mock_result.scalar.return_value = scalar_val
    if scalars_list is not None:
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = scalars_list
        mock_result.scalars.return_value = mock_scalars
    db.execute = AsyncMock(return_value=mock_result)
    return db


# ---------------------------------------------------------------------------
# Priority Scoring Tests
# ---------------------------------------------------------------------------


class TestPriorityScoring:
    def test_urgency_immediate(self):
        assert _calculate_urgency(5) == Decimal("1.0")

    def test_urgency_none(self):
        assert _calculate_urgency(None) == Decimal("1.0")

    def test_urgency_short_term(self):
        assert _calculate_urgency(15) == Decimal("0.7")

    def test_urgency_long_term(self):
        assert _calculate_urgency(60) == Decimal("0.4")

    def test_priority_score_calculation(self):
        score = _calculate_priority_score(
            Decimal("10000"), Decimal("1.0"), Decimal("80.00")
        )
        # 10000 * 1.0 * 0.8 = 8000
        assert score == Decimal("8000.00")

    def test_priority_score_with_lower_values(self):
        score = _calculate_priority_score(
            Decimal("500"), Decimal("0.7"), Decimal("60.00")
        )
        # 500 * 0.7 * 0.6 = 210
        assert score == Decimal("210.00")

    def test_assign_priority_high(self):
        assert _assign_priority_level(Decimal("6000")) == RecommendationPriority.HIGH

    def test_assign_priority_medium(self):
        assert _assign_priority_level(Decimal("2000")) == RecommendationPriority.MEDIUM

    def test_assign_priority_low(self):
        assert _assign_priority_level(Decimal("500")) == RecommendationPriority.LOW


# ---------------------------------------------------------------------------
# Recommendation CRUD Tests
# ---------------------------------------------------------------------------


class TestRecommendationCRUD:
    @pytest.mark.anyio
    async def test_get_recommendations_empty(self):
        db = _mock_db_with_execute(scalars_list=[])
        result = await get_recommendations(db)
        assert result == []

    @pytest.mark.anyio
    async def test_get_recommendations_with_filter(self):
        rec = _make_recommendation()
        db = _mock_db_with_execute(scalars_list=[rec])
        result = await get_recommendations(db, category="pricing")
        assert len(result) == 1

    @pytest.mark.anyio
    async def test_get_recommendation_found(self):
        rec = _make_recommendation()
        db = _mock_db_with_execute(return_val=rec)
        result = await get_recommendation(db, rec.id)
        assert result.id == rec.id

    @pytest.mark.anyio
    async def test_get_recommendation_not_found(self):
        db = _mock_db_with_execute(return_val=None)
        with pytest.raises(RecommendationNotFoundError):
            await get_recommendation(db, uuid.uuid4())

    @pytest.mark.anyio
    async def test_get_recommendation_history(self):
        rec = _make_recommendation(status=RecommendationStatus.APPLIED)
        db = _mock_db_with_execute(scalars_list=[rec])
        result = await get_recommendation_history(db)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Apply / Dismiss Tests
# ---------------------------------------------------------------------------


class TestApplyDismiss:
    @pytest.mark.anyio
    async def test_apply_already_processed(self):
        rec = _make_recommendation(status=RecommendationStatus.APPLIED)
        db = _mock_db_with_execute(return_val=rec)
        with pytest.raises(RecommendationAlreadyProcessedError):
            await apply_recommendation(db, rec.id, uuid.uuid4())

    @pytest.mark.anyio
    async def test_apply_expired(self):
        rec = _make_recommendation(
            expires_at=NOW - timedelta(days=1),
        )
        db = _mock_db_with_execute(return_val=rec)
        with pytest.raises(RecommendationExpiredError):
            await apply_recommendation(db, rec.id, uuid.uuid4())

    @pytest.mark.anyio
    async def test_dismiss_already_processed(self):
        rec = _make_recommendation(status=RecommendationStatus.DISMISSED)
        db = _mock_db_with_execute(return_val=rec)
        with pytest.raises(RecommendationAlreadyProcessedError):
            await dismiss_recommendation(db, rec.id, uuid.uuid4(), "Not needed")

    @pytest.mark.anyio
    async def test_dismiss_success(self):
        rec = _make_recommendation()
        db = _mock_db_with_execute(return_val=rec)
        result = await dismiss_recommendation(db, rec.id, uuid.uuid4(), "Manual action taken")
        assert result.status == RecommendationStatus.DISMISSED
        assert result.dismissed_reason == "Manual action taken"


# ---------------------------------------------------------------------------
# Impact Summary Tests
# ---------------------------------------------------------------------------


class TestImpactSummary:
    @pytest.mark.anyio
    async def test_impact_summary_empty(self):
        db = _mock_db_with_execute(scalars_list=[])
        result = await get_impact_summary(db)
        assert result["total_pending"] == 0
        assert result["projected_revenue_impact"] == Decimal("0")

    @pytest.mark.anyio
    async def test_impact_summary_with_recs(self):
        rec1 = _make_recommendation(
            category=RecommendationCategory.PRICING,
            expected_impact={"estimated_revenue_impact": "5000"},
        )
        rec2 = _make_recommendation(
            category=RecommendationCategory.CASHFLOW,
            expected_impact={"monthly_burn": "-2000", "estimated_revenue_impact": "0"},
        )
        db = _mock_db_with_execute(scalars_list=[rec1, rec2])
        result = await get_impact_summary(db)
        assert result["total_pending"] == 2
        assert result["projected_revenue_impact"] == Decimal("5000")
        assert result["projected_cost_savings"] == Decimal("2000")


# ---------------------------------------------------------------------------
# USD Accumulation Schedule Tests
# ---------------------------------------------------------------------------


class TestUSDAccumulationSchedule:
    @pytest.mark.anyio
    async def test_schedule_order_not_found(self):
        db = _mock_db_with_execute(return_val=None)
        with pytest.raises(Exception):
            await generate_usd_accumulation_schedule(db, uuid.uuid4())

    @pytest.mark.anyio
    async def test_schedule_generation(self):
        order_id = uuid.uuid4()
        order = MagicMock()
        order.id = order_id
        order.total_amount = Decimal("10000")
        order.expected_delivery_date = date.today() + timedelta(days=56)
        order.currency = "USD"

        db = _mock_db()
        call_count = 0

        async def mock_execute(query, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:
                # PurchaseOrder query
                mock_result.scalar_one_or_none.return_value = order
            elif call_count == 2:
                # Payment sum query
                mock_result.scalar.return_value = Decimal("3000")
            else:
                # FX rate query
                mock_result.scalar.return_value = Decimal("1500")
            return mock_result

        db.execute = AsyncMock(side_effect=mock_execute)

        with patch("src.fx.forecast_service.get_forecast_for_date", side_effect=Exception("no forecast")):
            result = await generate_usd_accumulation_schedule(db, order_id)

        assert result["order_id"] == str(order_id)
        # (10000 - 3000) * 0.70 = 4900
        assert result["total_usd_needed"] == str(Decimal("4900.00"))
        assert result["weeks"] == 8  # 56 // 7
        assert len(result["schedule"]) == 8


# ---------------------------------------------------------------------------
# USD Strategy Config Tests
# ---------------------------------------------------------------------------


class TestUSDStrategyConfig:
    @pytest.mark.anyio
    async def test_get_config_not_found(self):
        db = _mock_db_with_execute(return_val=None)
        with pytest.raises(USDStrategyConfigNotFoundError):
            await get_usd_strategy_config(db)

    @pytest.mark.anyio
    async def test_get_config_found(self):
        config = MagicMock(spec=USDStrategyConfig)
        config.id = uuid.uuid4()
        config.target_usd_balance = Decimal("50000")
        db = _mock_db_with_execute(return_val=config)
        result = await get_usd_strategy_config(db)
        assert result.target_usd_balance == Decimal("50000")


# ---------------------------------------------------------------------------
# Reorder Suggestion Tests
# ---------------------------------------------------------------------------


class TestReorderSuggestions:
    @pytest.mark.anyio
    async def test_get_suggestions_empty(self):
        db = _mock_db_with_execute(scalars_list=[])
        result = await get_reorder_suggestions(db)
        assert result == []

    @pytest.mark.anyio
    async def test_get_suggestion_not_found(self):
        db = _mock_db_with_execute(return_val=None)
        with pytest.raises(ReorderSuggestionNotFoundError):
            await get_reorder_suggestion(db, uuid.uuid4())

    @pytest.mark.anyio
    async def test_get_suggestion_found(self):
        suggestion = MagicMock(spec=ReorderSuggestion)
        suggestion.id = uuid.uuid4()
        suggestion.product_id = uuid.uuid4()
        suggestion.status = ReorderStatus.PENDING
        db = _mock_db_with_execute(return_val=suggestion)
        result = await get_reorder_suggestion(db, suggestion.product_id)
        assert result.product_id == suggestion.product_id

    @pytest.mark.anyio
    async def test_approve_reorder(self):
        suggestion = MagicMock(spec=ReorderSuggestion)
        suggestion.id = uuid.uuid4()
        suggestion.product_id = uuid.uuid4()
        suggestion.status = ReorderStatus.PENDING
        suggestion.suggested_order_quantity = 100
        db = _mock_db_with_execute(return_val=suggestion)
        result = await approve_reorder(db, suggestion.product_id)
        assert result.status == ReorderStatus.APPROVED


# ---------------------------------------------------------------------------
# Exception Tests
# ---------------------------------------------------------------------------


class TestExceptions:
    def test_recommendation_not_found(self):
        rid = uuid.uuid4()
        err = RecommendationNotFoundError(rid)
        assert str(rid) in str(err)

    def test_recommendation_expired(self):
        rid = uuid.uuid4()
        err = RecommendationExpiredError(rid, NOW)
        assert str(rid) in str(err)
        assert err.expired_at == NOW

    def test_recommendation_already_processed(self):
        rid = uuid.uuid4()
        err = RecommendationAlreadyProcessedError(rid, "applied")
        assert "applied" in str(err)

    def test_usd_strategy_not_found(self):
        err = USDStrategyConfigNotFoundError()
        assert "USD strategy" in str(err)

    def test_reorder_not_found(self):
        rid = uuid.uuid4()
        err = ReorderSuggestionNotFoundError(rid)
        assert str(rid) in str(err)


# ---------------------------------------------------------------------------
# Endpoint Tests
# ---------------------------------------------------------------------------


class TestAIEngineEndpoints:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self._original_overrides = app.dependency_overrides.copy()
        yield
        app.dependency_overrides = self._original_overrides

    def _override_auth(self):
        from src.auth.dependencies import get_current_active_user

        fake_user = MagicMock()
        app.dependency_overrides[get_current_active_user] = lambda: fake_user

    @pytest.mark.anyio
    async def test_list_recommendations_empty(self):
        self._override_auth()
        with patch("src.ai_engine.router.get_recommendations", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get("/api/v1/ai/recommendations")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 0
            assert data["items"] == []

    @pytest.mark.anyio
    async def test_generate_requires_auth(self):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/api/v1/ai/recommendations/generate")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_apply_requires_auth(self):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                f"/api/v1/ai/recommendations/{uuid.uuid4()}/apply"
            )
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_dismiss_requires_auth(self):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                f"/api/v1/ai/recommendations/{uuid.uuid4()}/dismiss",
                json={"reason": "test"},
            )
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_impact_summary_empty(self):
        self._override_auth()
        with patch("src.ai_engine.router.get_impact_summary", new_callable=AsyncMock) as mock_impact:
            mock_impact.return_value = {
                "total_pending": 0,
                "projected_revenue_impact": Decimal("0"),
                "projected_cost_savings": Decimal("0"),
                "by_category": [],
            }
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get("/api/v1/ai/recommendations/impact")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_recommendation_history_empty(self):
        self._override_auth()
        with patch("src.ai_engine.router.get_recommendation_history", new_callable=AsyncMock) as mock_hist:
            mock_hist.return_value = []
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get("/api/v1/ai/recommendations/history")
            assert resp.status_code == 200
            assert resp.json() == []

    @pytest.mark.anyio
    async def test_reorder_suggestions_empty(self):
        self._override_auth()
        with patch("src.ai_engine.router.get_reorder_suggestions", new_callable=AsyncMock) as mock_reorder:
            mock_reorder.return_value = []
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get("/api/v1/ai/reorder")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 0

    @pytest.mark.anyio
    async def test_generate_reorder_requires_auth(self):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/api/v1/ai/reorder/generate")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_usd_strategy_config_not_found(self):
        self._override_auth()
        with patch(
            "src.ai_engine.router.get_usd_strategy_config",
            new_callable=AsyncMock,
        ) as mock_config:
            mock_config.side_effect = USDStrategyConfigNotFoundError()
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get("/api/v1/ai/usd-strategy/config")
            assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_usd_strategy_config_create_requires_auth(self):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/v1/ai/usd-strategy/config",
                json={
                    "target_usd_balance": "50000",
                    "risk_tolerance": "moderate",
                },
            )
        assert resp.status_code == 401
