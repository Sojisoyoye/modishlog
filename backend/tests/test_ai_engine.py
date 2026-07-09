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
        from src.auth.dependencies import get_current_active_user, get_current_business_id

        fake_user = MagicMock()
        fake_business_id = uuid.uuid4()
        app.dependency_overrides[get_current_active_user] = lambda: fake_user
        app.dependency_overrides[get_current_business_id] = lambda: fake_business_id

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

    @pytest.mark.anyio
    async def test_usd_accumulation_schedule_unexpected_error_returns_500(self):
        self._override_auth()
        order_id = uuid.uuid4()
        with patch(
            "src.ai_engine.router.generate_usd_accumulation_schedule",
            new_callable=AsyncMock,
        ) as mock_sched:
            mock_sched.side_effect = RuntimeError("database connection lost")
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get(f"/api/v1/ai/usd-accumulation/{order_id}")
        assert resp.status_code == 500
        assert resp.json()["detail"] == "Internal server error"
        assert "database connection lost" not in resp.text

    @pytest.mark.anyio
    async def test_usd_accumulation_schedule_requires_auth(self):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(f"/api/v1/ai/usd-accumulation/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Business Isolation Tests (TDD - written before implementation)
# ---------------------------------------------------------------------------


class TestBusinessIsolation:
    @pytest.mark.anyio
    async def test_ai_recommendations_query_includes_business_id_filter(self):
        """Verify get_recommendations builds a WHERE clause containing the business_id."""
        from sqlalchemy import String
        from src.ai_engine.service import get_recommendations

        business_id = uuid.uuid4()
        captured_queries: list[str] = []

        async def capture_execute(query):
            # Compile query to string and capture it for assertion
            compiled = str(query.compile(compile_kwargs={"literal_binds": False}))
            captured_queries.append(compiled)
            r = MagicMock()
            r.scalars.return_value.all.return_value = []
            return r

        db = AsyncMock()
        db.execute = capture_execute

        await get_recommendations(db, business_id=business_id)

        assert len(captured_queries) == 1, "Expected exactly one DB query"
        query_str = captured_queries[0].lower()
        # The WHERE clause must reference business_id column
        assert "business_id" in query_str, (
            f"business_id filter missing from query: {captured_queries[0]}"
        )

    @pytest.mark.anyio
    async def test_reorder_suggestions_query_includes_business_id_filter(self):
        """Verify get_reorder_suggestions builds a WHERE clause containing the business_id."""
        from src.ai_engine.service import get_reorder_suggestions

        business_id = uuid.uuid4()
        captured_queries: list[str] = []

        async def capture_execute(query):
            compiled = str(query.compile(compile_kwargs={"literal_binds": False}))
            captured_queries.append(compiled)
            r = MagicMock()
            r.scalars.return_value.all.return_value = []
            return r

        db = AsyncMock()
        db.execute = capture_execute

        await get_reorder_suggestions(db, business_id=business_id)

        assert len(captured_queries) == 1, "Expected exactly one DB query"
        query_str = captured_queries[0].lower()
        assert "business_id" in query_str, (
            f"business_id filter missing from query: {captured_queries[0]}"
        )

    @pytest.mark.anyio
    async def test_get_recommendation_query_includes_business_id_filter(self):
        """Verify get_recommendation (single) scopes the WHERE to business_id."""
        from src.ai_engine.service import get_recommendation

        business_id = uuid.uuid4()
        captured_queries: list[str] = []

        async def capture_execute(query):
            compiled = str(query.compile(compile_kwargs={"literal_binds": False}))
            captured_queries.append(compiled)
            r = MagicMock()
            r.scalar_one_or_none.return_value = None
            return r

        db = AsyncMock()
        db.execute = capture_execute

        with pytest.raises(RecommendationNotFoundError):
            await get_recommendation(db, uuid.uuid4(), business_id=business_id)

        assert len(captured_queries) == 1
        query_str = captured_queries[0].lower()
        assert "business_id" in query_str, (
            f"business_id filter missing from get_recommendation query: {captured_queries[0]}"
        )

    @pytest.mark.anyio
    async def test_generate_reorder_suggestions_requires_business_id(self):
        """generate_reorder_suggestions must require business_id to avoid nullable FK crash."""
        import inspect
        from src.ai_engine.service import generate_reorder_suggestions

        sig = inspect.signature(generate_reorder_suggestions)
        param = sig.parameters.get("business_id")
        assert param is not None, "generate_reorder_suggestions must have business_id param"
        # Must NOT have a None default — the column is nullable=False
        assert param.default is inspect.Parameter.empty, (
            "business_id must be required (no default None) to prevent NOT NULL DB crash"
        )

    @pytest.mark.anyio
    async def test_generate_recommendations_stamps_business_id_on_records(self):
        """generate_all_recommendations must stamp every new record with business_id."""
        from src.ai_engine.service import generate_all_recommendations

        business_id = uuid.uuid4()
        user_id = uuid.uuid4()
        added_records: list = []

        db = AsyncMock()
        db.add = lambda obj: added_records.append(obj)
        db.flush = AsyncMock()

        # Return empty for the expire-old query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        # Fake generators that return a recommendation without business_id set
        fake_rec = _make_recommendation()
        fake_rec.business_id = None  # not yet set

        with (
            patch("src.ai_engine.service._generate_price_recommendations", new_callable=AsyncMock, return_value=[fake_rec]),
            patch("src.ai_engine.service._generate_order_timing_recommendations", new_callable=AsyncMock, return_value=[]),
            patch("src.ai_engine.service._generate_usd_hedge_recommendations", new_callable=AsyncMock, return_value=[]),
            patch("src.ai_engine.service._generate_liquidity_recommendations", new_callable=AsyncMock, return_value=[]),
        ):
            result = await generate_all_recommendations(db, user_id, business_id=business_id)

        # The record must have been stamped with business_id before db.add()
        assert len(added_records) == 1
        assert added_records[0].business_id == business_id, (
            "generate_all_recommendations must stamp rec.business_id before db.add()"
        )

    @pytest.mark.anyio
    async def test_recommendation_not_found_respects_business_id(self):
        """get_recommendation should 404 if rec belongs to a different business."""
        db = _mock_db_with_execute(return_val=None)
        with pytest.raises(RecommendationNotFoundError):
            await get_recommendation(db, uuid.uuid4(), business_id=uuid.uuid4())

    @pytest.mark.anyio
    async def test_impact_summary_query_includes_business_id_filter(self):
        """get_impact_summary must scope the query to the provided business_id."""
        from src.ai_engine.service import get_impact_summary

        business_id = uuid.uuid4()
        captured_queries: list[str] = []

        async def capture_execute(query):
            compiled = str(query.compile(compile_kwargs={"literal_binds": False}))
            captured_queries.append(compiled)
            r = MagicMock()
            r.scalars.return_value.all.return_value = []
            return r

        db = AsyncMock()
        db.execute = capture_execute

        result = await get_impact_summary(db, business_id=business_id)
        assert result["total_pending"] == 0
        assert len(captured_queries) == 1
        assert "business_id" in captured_queries[0].lower(), (
            f"business_id filter missing from get_impact_summary query: {captured_queries[0]}"
        )

    @pytest.mark.anyio
    async def test_recommendation_history_query_includes_business_id_filter(self):
        """get_recommendation_history must scope the query to the provided business_id."""
        from src.ai_engine.service import get_recommendation_history

        business_id = uuid.uuid4()
        captured_queries: list[str] = []

        async def capture_execute(query):
            compiled = str(query.compile(compile_kwargs={"literal_binds": False}))
            captured_queries.append(compiled)
            r = MagicMock()
            r.scalars.return_value.all.return_value = []
            return r

        db = AsyncMock()
        db.execute = capture_execute

        result = await get_recommendation_history(db, business_id=business_id)
        assert result == []
        assert len(captured_queries) == 1
        assert "business_id" in captured_queries[0].lower(), (
            f"business_id filter missing from get_recommendation_history query: {captured_queries[0]}"
        )


# ---------------------------------------------------------------------------
# Task #166 — ai_available + degraded_reason in RecommendationListResponse
# ---------------------------------------------------------------------------


class TestAIAvailableFlag:
    """RecommendationListResponse must expose ai_available and degraded_reason."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self._original_overrides = app.dependency_overrides.copy()
        yield
        app.dependency_overrides = self._original_overrides

    def _override_auth(self):
        from src.auth.dependencies import get_current_active_user, get_current_business_id

        fake_user = MagicMock()
        fake_business_id = uuid.uuid4()
        app.dependency_overrides[get_current_active_user] = lambda: fake_user
        app.dependency_overrides[get_current_business_id] = lambda: fake_business_id

    @pytest.mark.anyio
    async def test_ai_available_true_when_key_configured(self):
        """When ANTHROPIC_API_KEY is set, ai_available must be True."""
        self._override_auth()
        with patch("src.ai_engine.router.get_recommendations", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []
            with patch("src.ai_engine.router.settings") as mock_settings:
                mock_settings.ANTHROPIC_API_KEY = "sk-ant-test-key"
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.get("/api/v1/ai/recommendations")

        assert resp.status_code == 200
        data = resp.json()
        assert "ai_available" in data
        assert data["ai_available"] is True
        assert data["degraded_reason"] is None

    @pytest.mark.anyio
    async def test_ai_available_false_when_key_missing(self):
        """When ANTHROPIC_API_KEY is missing, ai_available must be False with a reason."""
        self._override_auth()
        with patch("src.ai_engine.router.get_recommendations", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []
            with patch("src.ai_engine.router.settings") as mock_settings:
                mock_settings.ANTHROPIC_API_KEY = ""
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.get("/api/v1/ai/recommendations")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ai_available"] is False
        assert data["degraded_reason"] is not None
        assert len(data["degraded_reason"]) > 0

    @pytest.mark.anyio
    async def test_ai_available_true_when_any_key_present(self):
        """Any non-empty key is accepted — format is the provider's concern, not ours."""
        self._override_auth()
        with patch("src.ai_engine.router.get_recommendations", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []
            with patch("src.ai_engine.router.settings") as mock_settings:
                mock_settings.ANTHROPIC_API_KEY = "any-provider-key-or-proxy-token"
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.get("/api/v1/ai/recommendations")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ai_available"] is True
        assert data["degraded_reason"] is None
