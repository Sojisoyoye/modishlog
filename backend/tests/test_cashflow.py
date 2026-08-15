"""Tests for cashflow domain: projections, DSCR, runway, stress scenarios."""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from src.auth.service import build_token
from src.cashflow.exceptions import LoanNotFoundError, ProjectionNotFoundError
from src.cashflow.models import (
    CashflowProjection,
    CostCategory,
    CostFrequency,
    LoanObligation,
    LoanPaymentSchedule,
    LoanStatus,
    OperatingCost,
    PaymentFrequency,
    TriageRecord,
    TriageStatus,
)
from src.core.security import get_password_hash
import src.suppliers.models  # noqa: F401 — registers Supplier mapper for PurchaseOrder

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


def _make_loan(**overrides):
    defaults = dict(
        lender_name="Test Bank",
        principal_amount=Decimal("1000000.000000"),
        outstanding_balance=Decimal("900000.000000"),
        interest_rate=Decimal("12.00"),
        term_months=24,
        start_date=date.today() - timedelta(days=60),
        end_date=date.today() + timedelta(days=660),
        payment_frequency=PaymentFrequency.MONTHLY,
        monthly_payment=Decimal("50000.000000"),
        currency="NGN",
        status=LoanStatus.ACTIVE,
        notes=None,
    )
    defaults.update(overrides)
    loan = LoanObligation(**defaults)
    loan.id = overrides.get("id", uuid.uuid4())
    loan.created_at = datetime.now(timezone.utc)
    loan.updated_at = datetime.now(timezone.utc)
    return loan


def _make_operating_cost(**overrides):
    defaults = dict(
        cost_name="Office Rent",
        cost_amount=Decimal("100000.000000"),
        frequency=CostFrequency.MONTHLY,
        monthly_equivalent=Decimal("100000.00"),
        category=CostCategory.RENT,
        is_active=True,
        created_by=uuid.uuid4(),
    )
    defaults.update(overrides)
    cost = OperatingCost(**defaults)
    cost.id = overrides.get("id", uuid.uuid4())
    cost.created_at = datetime.now(timezone.utc)
    cost.updated_at = datetime.now(timezone.utc)
    return cost


def _make_projection(**overrides):
    defaults = dict(
        projection_date=date.today(),
        horizon_months=6,
        monthly_buckets=[
            {
                "month": "2026-04",
                "projected_revenue": "500000.00",
                "projected_loan_payment": "50000.00",
                "projected_operating_costs": "100000.00",
                "projected_fx_obligations": "0.00",
                "net_cashflow": "350000.00",
                "cumulative_cashflow": "350000.00",
                "dscr": "8.000",
                "cash_runway_months": "999.0",
                "risk_rating": "LOW",
            },
        ],
        total_inflows=Decimal("500000.00"),
        total_outflows=Decimal("150000.00"),
        net_cashflow=Decimal("350000.00"),
        assumptions={"scenario_type": "BASE"},
        generated_by=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    proj = CashflowProjection(**defaults)
    proj.id = overrides.get("id", uuid.uuid4())
    return proj


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
# Frequency Normalization
# ---------------------------------------------------------------------------


class TestFrequencyNormalization:
    def test_daily_to_monthly(self):
        from src.cashflow.service import _normalize_to_monthly

        result = _normalize_to_monthly(Decimal("1000"), CostFrequency.DAILY)
        assert result == Decimal("30000.00")

    def test_weekly_to_monthly(self):
        from src.cashflow.service import _normalize_to_monthly

        result = _normalize_to_monthly(Decimal("1000"), CostFrequency.WEEKLY)
        assert result == Decimal("4330.00")

    def test_monthly_unchanged(self):
        from src.cashflow.service import _normalize_to_monthly

        result = _normalize_to_monthly(Decimal("5000"), CostFrequency.MONTHLY)
        assert result == Decimal("5000.00")

    def test_quarterly_to_monthly(self):
        from src.cashflow.service import _normalize_to_monthly

        result = _normalize_to_monthly(Decimal("30000"), CostFrequency.QUARTERLY)
        assert result == Decimal("10000.00")

    def test_annually_to_monthly(self):
        from src.cashflow.service import _normalize_to_monthly

        result = _normalize_to_monthly(Decimal("120000"), CostFrequency.ANNUALLY)
        assert result == Decimal("10000.00")


# ---------------------------------------------------------------------------
# Loan CRUD
# ---------------------------------------------------------------------------


class TestLoanCRUD:
    @pytest.mark.asyncio
    async def test_create_loan(self):
        from src.cashflow.service import create_loan

        db = _mock_db()
        db.execute = AsyncMock()

        class LoanData:
            lender_name = "Access Bank"
            principal_amount = Decimal("500000")
            interest_rate = Decimal("15.00")
            term_months = 12
            start_date = date.today()
            payment_frequency = PaymentFrequency.MONTHLY
            monthly_payment = Decimal("45000")
            currency = "NGN"
            notes = None

        biz_id = uuid.uuid4()
        with patch(
            "src.cashflow.service.invalidate_todays_projection",
            new_callable=AsyncMock,
        ):
            result = await create_loan(db, LoanData(), uuid.uuid4(), biz_id)
        assert result.lender_name == "Access Bank"
        assert result.outstanding_balance == Decimal("500000")
        assert db.add.called

    @pytest.mark.asyncio
    async def test_get_loans(self):
        from src.cashflow.service import get_loans

        loans = [_make_loan()]
        db = _mock_db_with_execute(scalars_result=loans)
        result = await get_loans(db, uuid.uuid4())
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_loan_not_found(self):
        from src.cashflow.service import get_loan

        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(LoanNotFoundError):
            await get_loan(db, uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_loan_success(self):
        from src.cashflow.service import get_loan

        loan = _make_loan()
        db = _mock_db_with_execute(scalar_result=loan)
        result = await get_loan(db, loan.id, uuid.uuid4())
        assert result.lender_name == "Test Bank"


# ---------------------------------------------------------------------------
# Operating Cost CRUD
# ---------------------------------------------------------------------------


class TestOperatingCostCRUD:
    @pytest.mark.asyncio
    async def test_create_operating_cost(self):
        from src.cashflow.service import create_operating_cost

        db = _mock_db()
        db.execute = AsyncMock()

        class CostData:
            cost_name = "Internet"
            cost_amount = Decimal("15000")
            frequency = CostFrequency.MONTHLY
            category = CostCategory.UTILITIES

        biz_id = uuid.uuid4()
        with patch(
            "src.cashflow.service.invalidate_todays_projection",
            new_callable=AsyncMock,
        ):
            result = await create_operating_cost(db, CostData(), uuid.uuid4(), biz_id)
        assert result.cost_name == "Internet"
        assert result.monthly_equivalent == Decimal("15000.00")
        assert db.add.called

    @pytest.mark.asyncio
    async def test_create_operating_cost_weekly(self):
        from src.cashflow.service import create_operating_cost

        db = _mock_db()
        db.execute = AsyncMock()

        class CostData:
            cost_name = "Transport"
            cost_amount = Decimal("5000")
            frequency = CostFrequency.WEEKLY
            category = CostCategory.TRANSPORT

        biz_id = uuid.uuid4()
        with patch(
            "src.cashflow.service.invalidate_todays_projection",
            new_callable=AsyncMock,
        ):
            result = await create_operating_cost(db, CostData(), uuid.uuid4(), biz_id)
        assert result.monthly_equivalent == Decimal("21650.00")

    @pytest.mark.asyncio
    async def test_get_operating_costs(self):
        from src.cashflow.service import get_operating_costs

        costs = [_make_operating_cost()]
        db = _mock_db_with_execute(scalars_result=costs)
        result = await get_operating_costs(db, uuid.uuid4())
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Projection cache invalidation (task 194)
# ---------------------------------------------------------------------------


class TestInvalidateTodaysProjection:
    """_get_or_regenerate_projection (task 191) only regenerates when the
    cached projection's date is in the past — so a loan/operating cost/order
    delivery added mid-day would otherwise not show up in the projection
    until the next calendar day. invalidate_todays_projection regenerates
    (inserts a fresh row) rather than deleting the stale one, since a saved
    StressScenario can reference a projection by id and deleting it would
    violate that FK."""

    @pytest.mark.asyncio
    async def test_regenerates_a_fresh_projection_for_the_given_business(self):
        from src.cashflow.service import invalidate_todays_projection

        db = _mock_db()
        business_id = uuid.uuid4()
        user_id = uuid.uuid4()

        with patch(
            "src.cashflow.service.generate_cashflow_projection",
            new_callable=AsyncMock,
        ) as mock_generate:
            await invalidate_todays_projection(db, user_id, business_id)

        mock_generate.assert_called_once_with(db, user_id, business_id)


class TestProjectionInvalidationHooks:
    """create_loan and create_operating_cost must invalidate today's cached
    projection so it's regenerated on next read, reflecting the new data."""

    @pytest.mark.asyncio
    async def test_create_loan_invalidates_todays_projection(self):
        from src.cashflow.service import create_loan

        db = _mock_db()
        db.execute = AsyncMock()

        class LoanData:
            lender_name = "Access Bank"
            principal_amount = Decimal("500000")
            interest_rate = Decimal("15.00")
            term_months = 12
            start_date = date.today()
            payment_frequency = PaymentFrequency.MONTHLY
            monthly_payment = Decimal("45000")
            currency = "NGN"
            notes = None

        business_id = uuid.uuid4()
        user_id = uuid.uuid4()
        with patch(
            "src.cashflow.service.invalidate_todays_projection",
            new_callable=AsyncMock,
        ) as mock_invalidate:
            await create_loan(db, LoanData(), user_id, business_id)
        mock_invalidate.assert_called_once_with(db, user_id, business_id)

    @pytest.mark.asyncio
    async def test_create_operating_cost_invalidates_todays_projection(self):
        from src.cashflow.service import create_operating_cost

        db = _mock_db()
        db.execute = AsyncMock()

        class CostData:
            cost_name = "Internet"
            cost_amount = Decimal("15000")
            frequency = CostFrequency.MONTHLY
            category = CostCategory.UTILITIES

        business_id = uuid.uuid4()
        user_id = uuid.uuid4()
        with patch(
            "src.cashflow.service.invalidate_todays_projection",
            new_callable=AsyncMock,
        ) as mock_invalidate:
            await create_operating_cost(db, CostData(), user_id, business_id)
        mock_invalidate.assert_called_once_with(db, user_id, business_id)


# ---------------------------------------------------------------------------
# DSCR Calculation
# ---------------------------------------------------------------------------


class TestDSCR:
    def test_dscr_healthy(self):
        from src.cashflow.service import _calculate_dscr

        dscr = _calculate_dscr(Decimal("1000000"), Decimal("600000"), Decimal("200000"))
        assert dscr == Decimal("2.000")

    def test_dscr_no_debt(self):
        from src.cashflow.service import _calculate_dscr

        dscr = _calculate_dscr(Decimal("1000000"), Decimal("600000"), Decimal("0"))
        assert dscr == Decimal("999.000")

    def test_dscr_below_1(self):
        from src.cashflow.service import _calculate_dscr

        dscr = _calculate_dscr(Decimal("500000"), Decimal("400000"), Decimal("200000"))
        assert dscr == Decimal("0.500")

    @pytest.mark.asyncio
    async def test_get_current_dscr(self):
        from src.cashflow.service import get_current_dscr

        db = _mock_db()
        # Three sequential calls: revenue sum, opex sum, loan sum
        rev_result = MagicMock()
        rev_result.scalar.return_value = Decimal("3000000")  # 90d revenue -> 1M/month
        opex_result = MagicMock()
        opex_result.scalar.return_value = Decimal("300000")
        loan_result = MagicMock()
        loan_result.scalar.return_value = Decimal("200000")

        db.execute = AsyncMock(side_effect=[rev_result, opex_result, loan_result])

        result = await get_current_dscr(db, uuid.uuid4())
        assert result["dscr"] == Decimal("3.500")  # (1M - 300k) / 200k
        assert result["color"] == "green"
        # A real loan payment exists — DSCR is a meaningful, finite ratio.
        assert result["dscr_is_finite"] is True

    @pytest.mark.asyncio
    async def test_get_current_dscr_no_loan_marks_dscr_not_finite(self):
        """Task 187 — a debt-free business has no debt-service obligation, so
        DSCR is mathematically undefined. The 999 sentinel must never be
        displayed as a raw ratio; dscr_is_finite=False tells the frontend to
        show a friendly 'No debt' state instead."""
        from src.cashflow.service import get_current_dscr

        db = _mock_db()
        rev_result = MagicMock()
        rev_result.scalar.return_value = Decimal("3000000")
        opex_result = MagicMock()
        opex_result.scalar.return_value = Decimal("300000")
        loan_result = MagicMock()
        loan_result.scalar.return_value = Decimal("0")

        db.execute = AsyncMock(side_effect=[rev_result, opex_result, loan_result])

        result = await get_current_dscr(db, uuid.uuid4())
        assert result["dscr"] == Decimal("999.000")
        assert result["dscr_is_finite"] is False
        # Debt-free is the best case, not a risk signal — color stays green.
        assert result["color"] == "green"


# ---------------------------------------------------------------------------
# Risk Rating
# ---------------------------------------------------------------------------


class TestRiskRating:
    def test_low_risk(self):
        from src.cashflow.service import _assign_risk_rating

        assert _assign_risk_rating(Decimal("2.0"), Decimal("8")) == "LOW"

    def test_medium_risk_dscr(self):
        from src.cashflow.service import _assign_risk_rating

        assert _assign_risk_rating(Decimal("1.2"), Decimal("8")) == "MEDIUM"

    def test_medium_risk_runway(self):
        from src.cashflow.service import _assign_risk_rating

        assert _assign_risk_rating(Decimal("2.0"), Decimal("4")) == "MEDIUM"

    def test_high_risk_dscr(self):
        from src.cashflow.service import _assign_risk_rating

        assert _assign_risk_rating(Decimal("0.8"), Decimal("8")) == "HIGH"

    def test_high_risk_runway(self):
        from src.cashflow.service import _assign_risk_rating

        assert _assign_risk_rating(Decimal("2.0"), Decimal("2")) == "HIGH"


# ---------------------------------------------------------------------------
# Scenario Parameters
# ---------------------------------------------------------------------------


class TestScenarioParams:
    def test_base_scenario(self):
        from src.cashflow.service import _get_scenario_params

        params = _get_scenario_params("BASE")
        assert params["revenue_shock_pct"] == Decimal("0")
        assert params["fx_shock_pct"] == Decimal("0")

    def test_fx_shock_10(self):
        from src.cashflow.service import _get_scenario_params

        params = _get_scenario_params("FX_SHOCK_10")
        assert params["fx_shock_pct"] == Decimal("10")

    def test_demand_drop_20(self):
        from src.cashflow.service import _get_scenario_params

        params = _get_scenario_params("DEMAND_DROP_20")
        assert params["revenue_shock_pct"] == Decimal("-20")

    def test_combined_stress(self):
        from src.cashflow.service import _get_scenario_params

        params = _get_scenario_params("COMBINED_STRESS")
        assert params["revenue_shock_pct"] == Decimal("-20")
        assert params["fx_shock_pct"] == Decimal("20")


# ---------------------------------------------------------------------------
# Cash Runway
# ---------------------------------------------------------------------------


class TestGetOrRegenerateProjection:
    """Task 191 (ST-701 criterion 5) — daily recalculation, computed lazily
    on next access rather than via a background scheduler."""

    @pytest.mark.asyncio
    async def test_reuses_projection_generated_today(self):
        from src.cashflow.service import _get_or_regenerate_projection

        proj = _make_projection(projection_date=date.today())
        with (
            patch(
                "src.cashflow.service.get_latest_projection",
                new_callable=AsyncMock,
                return_value=proj,
            ),
            patch(
                "src.cashflow.service.generate_cashflow_projection",
                new_callable=AsyncMock,
            ) as mock_generate,
        ):
            db = _mock_db()
            result = await _get_or_regenerate_projection(db, uuid.uuid4(), uuid.uuid4())
        assert result is proj
        mock_generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_regenerates_when_projection_is_stale(self):
        from src.cashflow.service import _get_or_regenerate_projection

        stale_proj = _make_projection(projection_date=date.today() - timedelta(days=1))
        fresh_proj = _make_projection(projection_date=date.today())
        with (
            patch(
                "src.cashflow.service.get_latest_projection",
                new_callable=AsyncMock,
                return_value=stale_proj,
            ),
            patch(
                "src.cashflow.service.generate_cashflow_projection",
                new_callable=AsyncMock,
                return_value=fresh_proj,
            ) as mock_generate,
        ):
            db = _mock_db()
            result = await _get_or_regenerate_projection(db, uuid.uuid4(), uuid.uuid4())
        assert result is fresh_proj
        mock_generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generates_when_none_exists(self):
        from src.cashflow.service import _get_or_regenerate_projection

        fresh_proj = _make_projection()
        with (
            patch(
                "src.cashflow.service.get_latest_projection",
                new_callable=AsyncMock,
                side_effect=ProjectionNotFoundError(),
            ),
            patch(
                "src.cashflow.service.generate_cashflow_projection",
                new_callable=AsyncMock,
                return_value=fresh_proj,
            ) as mock_generate,
        ):
            db = _mock_db()
            result = await _get_or_regenerate_projection(db, uuid.uuid4(), uuid.uuid4())
        assert result is fresh_proj
        mock_generate.assert_called_once()


class TestCashRunway:
    @pytest.mark.asyncio
    async def test_runway_all_positive(self):
        from src.cashflow.service import calculate_cash_runway

        proj = _make_projection()
        db = _mock_db_with_execute(scalar_result=proj)
        result = await calculate_cash_runway(db, uuid.uuid4(), uuid.uuid4())
        assert result["runway_months"] == Decimal("999.0")
        assert result["avg_monthly_burn"] == Decimal("0")
        # Task 187 — cash-flow-positive with no burn means runway is
        # mathematically infinite; the raw 999 sentinel must never be
        # displayed. runway_months_is_finite=False signals the frontend to
        # show a friendly 'No burn' state instead.
        assert result["runway_months_is_finite"] is False

    @pytest.mark.asyncio
    async def test_runway_with_negative_months(self):
        from src.cashflow.service import calculate_cash_runway

        proj = _make_projection(
            monthly_buckets=[
                {
                    "month": "2026-04",
                    "net_cashflow": "-100000.00",
                    "cumulative_cashflow": "400000.00",
                    "dscr": "0.800",
                    "cash_runway_months": "4.0",
                    "risk_rating": "HIGH",
                    "projected_revenue": "300000.00",
                    "projected_loan_payment": "200000.00",
                    "projected_operating_costs": "200000.00",
                    "projected_fx_obligations": "0.00",
                },
                {
                    "month": "2026-05",
                    "net_cashflow": "-100000.00",
                    "cumulative_cashflow": "300000.00",
                    "dscr": "0.800",
                    "cash_runway_months": "3.0",
                    "risk_rating": "HIGH",
                    "projected_revenue": "300000.00",
                    "projected_loan_payment": "200000.00",
                    "projected_operating_costs": "200000.00",
                    "projected_fx_obligations": "0.00",
                },
            ],
        )
        db = _mock_db_with_execute(scalar_result=proj)
        result = await calculate_cash_runway(db, uuid.uuid4(), uuid.uuid4())
        assert result["runway_months"] == Decimal("3.0")
        assert result["avg_monthly_burn"] == Decimal("-100000.00")
        # A real burn rate exists — runway is a meaningful, finite number.
        assert result["runway_months_is_finite"] is True


# ---------------------------------------------------------------------------
# Liquidity Trend (task 191, ST-702 criterion 4 — 7-day trend arrows)
# ---------------------------------------------------------------------------


def _make_snapshot(**overrides):
    from src.cashflow.models import LiquiditySnapshot

    defaults = dict(
        business_id=uuid.uuid4(),
        snapshot_date=date.today() - timedelta(days=7),
        cash_runway_months=None,
        cash_runway_is_finite=None,
        dscr=None,
        dscr_is_finite=None,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    snap = LiquiditySnapshot(**defaults)
    snap.id = overrides.get("id", uuid.uuid4())
    return snap


class TestTrendDirection:
    def test_higher_current_is_up(self):
        from src.cashflow.service import _trend_direction

        assert _trend_direction(Decimal("5.0"), True, Decimal("3.0"), True) == "up"

    def test_lower_current_is_down(self):
        from src.cashflow.service import _trend_direction

        assert _trend_direction(Decimal("3.0"), True, Decimal("5.0"), True) == "down"

    def test_equal_is_flat(self):
        from src.cashflow.service import _trend_direction

        assert _trend_direction(Decimal("5.0"), True, Decimal("5.0"), True) == "flat"

    def test_became_infinite_is_up(self):
        """Went from a real burn rate to no burn at all — an improvement."""
        from src.cashflow.service import _trend_direction

        assert _trend_direction(Decimal("999.0"), False, Decimal("3.0"), True) == "up"

    def test_was_infinite_now_finite_is_down(self):
        """Went from no burn to a real burn rate — a deterioration."""
        from src.cashflow.service import _trend_direction

        assert _trend_direction(Decimal("3.0"), True, Decimal("999.0"), False) == "down"

    def test_both_infinite_is_flat(self):
        from src.cashflow.service import _trend_direction

        assert (
            _trend_direction(Decimal("999.0"), False, Decimal("999.0"), False) == "flat"
        )


class TestGetRunwayTrend:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_old_snapshot(self):
        from src.cashflow.service import get_runway_trend

        db = _mock_db_with_execute(scalar_result=None)
        result = await get_runway_trend(db, uuid.uuid4(), Decimal("5.0"), True)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_old_snapshot_has_no_runway_value(self):
        """A snapshot may exist for that day from a /dscr call that ran
        before /cash-runway ever did — its runway field is still null."""
        from src.cashflow.service import get_runway_trend

        old = _make_snapshot(cash_runway_months=None)
        db = _mock_db_with_execute(scalar_result=old)
        result = await get_runway_trend(db, uuid.uuid4(), Decimal("5.0"), True)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_up_when_runway_improved(self):
        from src.cashflow.service import get_runway_trend

        old = _make_snapshot(
            cash_runway_months=Decimal("3.0"), cash_runway_is_finite=True
        )
        db = _mock_db_with_execute(scalar_result=old)
        result = await get_runway_trend(db, uuid.uuid4(), Decimal("5.0"), True)
        assert result == "up"


class TestGetDscrTrend:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_old_snapshot(self):
        from src.cashflow.service import get_dscr_trend

        db = _mock_db_with_execute(scalar_result=None)
        result = await get_dscr_trend(db, uuid.uuid4(), Decimal("1.5"), True)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_down_when_dscr_worsened(self):
        from src.cashflow.service import get_dscr_trend

        old = _make_snapshot(dscr=Decimal("2.0"), dscr_is_finite=True)
        db = _mock_db_with_execute(scalar_result=old)
        result = await get_dscr_trend(db, uuid.uuid4(), Decimal("1.2"), True)
        assert result == "down"


class TestRecordSnapshots:
    """record_runway_snapshot/record_dscr_snapshot use an atomic pg_insert
    ON CONFLICT DO UPDATE (single execute, no db.add) rather than
    SELECT-then-INSERT, because /cash-runway and /dscr are fetched
    concurrently by the frontend (forkJoin) — two racing requests for a
    business with no snapshot row yet would otherwise both try to INSERT
    and one would hit the unique constraint. Same pattern already
    established in src/settings/service.py's update_app_setting()."""

    @pytest.mark.asyncio
    async def test_record_runway_snapshot_upserts_via_single_execute(self):
        from src.cashflow.service import record_runway_snapshot

        db = _mock_db()
        db.execute = AsyncMock(return_value=MagicMock())
        await record_runway_snapshot(db, uuid.uuid4(), Decimal("4.0"), True)
        db.execute.assert_called_once()
        db.add.assert_not_called()
        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_dscr_snapshot_upserts_via_single_execute(self):
        from src.cashflow.service import record_dscr_snapshot

        db = _mock_db()
        db.execute = AsyncMock(return_value=MagicMock())
        await record_dscr_snapshot(db, uuid.uuid4(), Decimal("1.8"), True)
        db.execute.assert_called_once()
        db.add.assert_not_called()
        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_runway_snapshot_conflict_update_only_touches_runway_columns(
        self,
    ):
        """The ON CONFLICT SET clause must not overwrite dscr/dscr_is_finite
        — otherwise a /cash-runway call later in the day would clobber
        whatever /dscr already wrote for today."""
        from src.cashflow.service import record_runway_snapshot

        db = _mock_db()
        db.execute = AsyncMock(return_value=MagicMock())
        await record_runway_snapshot(db, uuid.uuid4(), Decimal("4.0"), True)
        stmt = db.execute.call_args[0][0]
        compiled = stmt.compile(dialect=postgresql.dialect())
        set_clause = str(compiled).split("DO UPDATE SET")[1]
        assert "cash_runway_months" in set_clause
        assert "cash_runway_is_finite" in set_clause
        assert "dscr" not in set_clause


# ---------------------------------------------------------------------------
# Liquidity Alerts
# ---------------------------------------------------------------------------


class TestLiquidityAlerts:
    @pytest.mark.asyncio
    async def test_no_projection_no_alerts(self):
        from src.cashflow.service import check_liquidity_alerts

        db = _mock_db_with_execute(scalar_result=None)
        result = await check_liquidity_alerts(db, uuid.uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_alerts_negative_cashflow(self):
        from src.cashflow.service import check_liquidity_alerts

        proj = _make_projection(
            monthly_buckets=[
                {
                    "month": "2026-04",
                    "net_cashflow": "-50000.00",
                    "cumulative_cashflow": "200000.00",
                    "dscr": "0.800",
                    "cash_runway_months": "3.5",
                    "risk_rating": "HIGH",
                    "projected_revenue": "300000.00",
                    "projected_loan_payment": "200000.00",
                    "projected_operating_costs": "150000.00",
                    "projected_fx_obligations": "0.00",
                },
            ],
        )
        db = _mock_db_with_execute(scalar_result=proj)
        result = await check_liquidity_alerts(db, uuid.uuid4())
        # Should have: negative_cashflow (WARNING), dscr_below_1 (CRITICAL),
        # low_runway (WARNING)
        types = [a["type"] for a in result]
        assert "negative_cashflow" in types
        assert "dscr_below_1" in types
        assert "low_runway" in types

    @pytest.mark.asyncio
    async def test_alerts_critical_cumulative(self):
        from src.cashflow.service import check_liquidity_alerts

        proj = _make_projection(
            monthly_buckets=[
                {
                    "month": "2026-04",
                    "net_cashflow": "-200000.00",
                    "cumulative_cashflow": "-50000.00",
                    "dscr": "0.500",
                    "cash_runway_months": "0",
                    "risk_rating": "HIGH",
                    "projected_revenue": "100000.00",
                    "projected_loan_payment": "200000.00",
                    "projected_operating_costs": "100000.00",
                    "projected_fx_obligations": "0.00",
                },
            ],
        )
        db = _mock_db_with_execute(scalar_result=proj)
        result = await check_liquidity_alerts(db, uuid.uuid4())
        severities = [a["severity"] for a in result]
        assert "CRITICAL" in severities
        types = [a["type"] for a in result]
        assert "negative_cumulative" in types


# ---------------------------------------------------------------------------
# Projection Summary Helpers
# ---------------------------------------------------------------------------


class TestProjectionHelpers:
    def test_avg_dscr_from_buckets(self):
        from src.cashflow.service import _avg_dscr_from_buckets

        buckets = [{"dscr": "2.000"}, {"dscr": "1.000"}]
        assert _avg_dscr_from_buckets(buckets) == Decimal("1.500")

    def test_avg_dscr_empty(self):
        from src.cashflow.service import _avg_dscr_from_buckets

        assert _avg_dscr_from_buckets([]) == Decimal("0")

    def test_avg_dscr_excludes_no_debt_sentinel_from_average(self):
        """Task 187 — a debt-free month's dscr=999 sentinel must not pull a
        blended average up to a meaningless value; only real (finite) DSCR
        months should count."""
        from src.cashflow.service import _avg_dscr_from_buckets

        buckets = [{"dscr": "2.000"}, {"dscr": "999.000"}]
        assert _avg_dscr_from_buckets(buckets) == Decimal("2.000")

    def test_avg_dscr_all_sentinel_returns_sentinel(self):
        from src.cashflow.service import _avg_dscr_from_buckets

        buckets = [{"dscr": "999.000"}, {"dscr": "999.000"}]
        assert _avg_dscr_from_buckets(buckets) == Decimal("999.000")

    def test_avg_runway_from_buckets(self):
        from src.cashflow.service import _avg_runway_from_buckets

        buckets = [{"cash_runway_months": "6.0"}, {"cash_runway_months": "4.0"}]
        assert _avg_runway_from_buckets(buckets) == 5

    def test_avg_runway_excludes_infinite_sentinel_from_average(self):
        """Task 187 — a no-burn month's runway=999 sentinel must not pull a
        blended average up to a meaningless value; only real (finite)
        runway months should count."""
        from src.cashflow.service import _avg_runway_from_buckets

        buckets = [{"cash_runway_months": "4.0"}, {"cash_runway_months": "999.0"}]
        assert _avg_runway_from_buckets(buckets) == 4

    def test_avg_runway_all_sentinel_returns_sentinel(self):
        from src.cashflow.service import _avg_runway_from_buckets

        buckets = [{"cash_runway_months": "999.0"}, {"cash_runway_months": "999.0"}]
        assert _avg_runway_from_buckets(buckets) == 999

    @pytest.mark.asyncio
    async def test_summarize_projection(self):
        from src.cashflow.service import _summarize_projection

        proj = _make_projection()  # assumptions={"scenario_type": "BASE"}
        db = _mock_db()
        with patch(
            "src.cashflow.service.calculate_portfolio_margin",
            new_callable=AsyncMock,
            return_value={"blended_margin": Decimal("40.00")},
        ):
            summary = await _summarize_projection(db, proj, uuid.uuid4())
        assert summary["risk_rating"] == "LOW"
        assert summary["avg_dscr"] == 8.0
        assert "net_cashflow" in summary
        # Task 187 — default fixture bucket: dscr=8.000 (finite),
        # cash_runway_months=999.0 (infinite sentinel).
        assert summary["avg_dscr_is_finite"] is True
        assert summary["cash_runway_is_finite"] is False
        # Task 188 — BASE scenario has no FX shock, so margin is unchanged
        # from the actual current blended margin.
        assert summary["margin_pct"] == 40.0

    @pytest.mark.asyncio
    async def test_summarize_projection_fx_shock_reduces_margin(self):
        """Task 188 (ST-703 criterion 3) — an FX shock increases landed
        cost proportionally (assuming selling prices don't react), so
        margin_pct must erode, not stay fixed."""
        from src.cashflow.service import _summarize_projection

        proj = _make_projection(assumptions={"scenario_type": "FX_SHOCK_20"})
        db = _mock_db()
        with patch(
            "src.cashflow.service.calculate_portfolio_margin",
            new_callable=AsyncMock,
            return_value={"blended_margin": Decimal("40.00")},
        ):
            summary = await _summarize_projection(db, proj, uuid.uuid4())
        # cogs_ratio = 0.60; stressed = 0.60 * 1.20 = 0.72; margin = 28.00
        assert summary["margin_pct"] == 28.0

    @pytest.mark.asyncio
    async def test_summarize_projection_demand_drop_leaves_margin_unchanged(self):
        """Task 188 — a pure demand-drop scenario (no FX shock) doesn't
        change the cost-to-price ratio, so margin_pct is unaffected — only
        cashflow/revenue figures move. Margin % is volume-independent."""
        from src.cashflow.service import _summarize_projection

        proj = _make_projection(assumptions={"scenario_type": "DEMAND_DROP_20"})
        db = _mock_db()
        with patch(
            "src.cashflow.service.calculate_portfolio_margin",
            new_callable=AsyncMock,
            return_value={"blended_margin": Decimal("40.00")},
        ):
            summary = await _summarize_projection(db, proj, uuid.uuid4())
        assert summary["margin_pct"] == 40.0


# ---------------------------------------------------------------------------
# Cross-tenant scoping (task 205)
# ---------------------------------------------------------------------------


class TestCashflowCrossTenantScoping:
    """Found 2026-08-15 in a codebase-wide cross-tenant audit:
    _calculate_fx_obligations() had no business_id filter at all and is
    called for every month bucket of every projection -- hit on nearly
    every /cashflow/projection, /cash-runway, /dscr request via the daily-
    regen path. build_payment_calendar()'s FX section had the same gap
    (its sibling loan-schedule and operating-costs sections were already
    scoped). generate_triage_recommendations() received business_id but
    never passed it to get_liquidation_candidates(), which already
    supports it -- so LIQUIDATE recommendations pooled every business's
    inventory batches."""

    @pytest.mark.asyncio
    async def test_calculate_fx_obligations_scopes_purchase_orders(self):
        from src.cashflow.service import _calculate_fx_obligations

        business_id = uuid.uuid4()
        captured_queries = []

        async def capture_execute(stmt):
            captured_queries.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
            result = MagicMock()
            result.all.return_value = []
            return result

        db = AsyncMock()
        db.execute = capture_execute

        await _calculate_fx_obligations(
            db, business_id, date(2026, 4, 1), date(2026, 4, 30)
        )

        assert len(captured_queries) == 1
        compiled = captured_queries[0].lower()
        assert "purchase_orders.business_id" in compiled
        assert business_id.hex in compiled.replace("-", "")

    @pytest.mark.asyncio
    async def test_build_payment_calendar_fx_section_scopes_purchase_orders(self):
        from src.cashflow.service import build_payment_calendar

        business_id = uuid.uuid4()
        captured_queries = []

        async def capture_execute(stmt):
            captured_queries.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
            result = MagicMock()
            result.all.return_value = []
            result.scalars.return_value.all.return_value = []
            result.scalar.return_value = None
            return result

        db = AsyncMock()
        db.execute = capture_execute

        await build_payment_calendar(
            db, business_id, horizon_days=30, starting_balance=Decimal("0")
        )

        fx_queries = [
            q for q in captured_queries if "purchase_orders" in q.lower()
        ]
        assert len(fx_queries) == 1
        compiled = fx_queries[0].lower()
        assert "purchase_orders.business_id" in compiled
        assert business_id.hex in compiled.replace("-", "")

    @pytest.mark.asyncio
    async def test_generate_triage_recommendations_scopes_liquidation_candidates(self):
        from src.cashflow.service import generate_triage_recommendations

        business_id = uuid.uuid4()
        db = _mock_db()
        default_result = MagicMock()
        default_result.scalar_one_or_none.return_value = None
        default_result.scalars.return_value.all.return_value = []
        default_result.one.return_value = (0, Decimal("0"))
        db.execute = AsyncMock(return_value=default_result)

        with patch(
            "src.cashflow.service.get_active_triage",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "src.inventory.service.get_liquidation_candidates",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_candidates:
            await generate_triage_recommendations(db, business_id)

        mock_candidates.assert_called_once_with(
            db, Decimal("0"), business_id=business_id
        )


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestCashflowEndpoints:
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
        from src.auth.dependencies import (
            get_current_active_user,
            get_current_business_id,
        )

        biz_id = uuid.uuid4()
        u = _make_user()
        u.business_id = biz_id

        async def _fake_auth():
            return u

        async def _fake_business_id():
            return biz_id

        self.app.dependency_overrides[get_current_active_user] = _fake_auth
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id

    def test_list_loans_empty(self):
        self._override_auth()
        db = _mock_db_with_execute(scalars_result=[])
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/cashflow/loans")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_loan_requires_auth(self):
        db = _mock_db()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/cashflow/loans",
                json={
                    "lender_name": "Bank",
                    "principal_amount": "500000",
                    "interest_rate": "12",
                    "term_months": 12,
                    "start_date": "2026-01-01",
                    "monthly_payment": "45000",
                },
            )
        assert resp.status_code == 401

    def test_get_loan_not_found(self):
        self._override_auth()
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/cashflow/loans/{fake_id}")
        assert resp.status_code == 404

    def test_list_operating_costs_empty(self):
        self._override_auth()
        db = _mock_db_with_execute(scalars_result=[])
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/cashflow/operating-costs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_operating_cost_requires_auth(self):
        db = _mock_db()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/cashflow/operating-costs",
                json={
                    "cost_name": "Rent",
                    "cost_amount": "100000",
                    "frequency": "monthly",
                    "category": "rent",
                },
            )
        assert resp.status_code == 401

    def test_projection_requires_auth(self):
        db = _mock_db()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/cashflow/projection")
        assert resp.status_code == 401

    def test_scenario_projection_invalid(self):
        db = _mock_db()
        self._override_db(db)
        headers, _ = self._auth_headers()
        with TestClient(self.app) as client:
            resp = client.get(
                "/api/v1/cashflow/projection/INVALID_SCENARIO",
                headers=headers,
            )
        assert resp.status_code == 400

    def test_run_scenario_requires_auth(self):
        db = _mock_db()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/cashflow/run-scenario",
                json={"scenario_type": "FX_SHOCK_10"},
            )
        assert resp.status_code == 401

    def test_list_scenarios_empty(self):
        self._override_auth()
        db = _mock_db_with_execute(scalars_result=[])
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/cashflow/scenarios")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_alerts_empty(self):
        self._override_auth()
        # No projection found -> returns empty alerts
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/cashflow/alerts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_cash_runway_generates_projection_when_none_exists(self):
        """Task 191 — GET /cashflow/cash-runway now always resolves a real
        projection (generating one via `_get_or_regenerate_projection` if
        none exists yet), instead of the old hardcoded runway_months=0
        placeholder. A brand-new business with no revenue/cost data has no
        burn months in its generated projection, so runway is genuinely
        infinite (is_finite=False) — not a fake finite zero."""
        self._override_auth()
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/cashflow/cash-runway")
        assert resp.status_code == 200
        body = resp.json()
        assert Decimal(body["runway_months"]) == Decimal("999.0")
        assert body["runway_months_is_finite"] is False
        # No 7-day-old snapshot exists yet -> no trend to show.
        assert body["runway_trend"] is None

    def test_dscr_endpoint_returns_dscr_is_finite(self):
        """Task 187 — GET /cashflow/dscr must surface dscr_is_finite so the
        frontend can render 'No debt' instead of a raw 999.00 ratio."""
        self._override_auth()
        db = _mock_db()
        rev_result = MagicMock()
        rev_result.scalar.return_value = Decimal("3000000")
        opex_result = MagicMock()
        opex_result.scalar.return_value = Decimal("300000")
        loan_result = MagicMock()
        loan_result.scalar.return_value = Decimal("0")
        # Task 191 — dscr_endpoint also upserts today's snapshot (SELECT,
        # not found -> INSERT via db.add/db.flush, no extra execute) and
        # looks up a 7-day-old snapshot for the trend (SELECT, none yet).
        snapshot_lookup = MagicMock()
        snapshot_lookup.scalar_one_or_none.return_value = None
        trend_lookup = MagicMock()
        trend_lookup.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(
            side_effect=[
                rev_result,
                opex_result,
                loan_result,
                snapshot_lookup,
                trend_lookup,
            ]
        )
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/cashflow/dscr")
        assert resp.status_code == 200
        body = resp.json()
        assert Decimal(body["dscr"]) == Decimal("999.000")
        assert body["dscr_is_finite"] is False
        # No 7-day-old snapshot exists yet -> no trend to show.
        assert body["dscr_trend"] is None

    def test_triage_status_none(self):
        self._override_auth()
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/cashflow/triage-status")
        assert resp.status_code == 200
        assert resp.json() is None

    def test_payment_calendar_empty(self):
        """Payment calendar returns empty when no scheduled payments."""
        self._override_auth()
        db = _mock_db()
        # Sequential calls: loan schedules, opex, fx_rate, fx_orders, projection
        loan_result = MagicMock()
        loan_result.all.return_value = []
        opex_result = MagicMock()
        opex_scalars = MagicMock()
        opex_scalars.all.return_value = []
        opex_result.scalars.return_value = opex_scalars
        fx_rate_result = MagicMock()
        fx_rate_result.scalar.return_value = None
        fx_orders_result = MagicMock()
        fx_orders_scalars = MagicMock()
        fx_orders_scalars.all.return_value = []
        fx_orders_result.scalars.return_value = fx_orders_scalars
        proj_result = MagicMock()
        proj_result.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(
            side_effect=[
                loan_result,
                opex_result,
                fx_rate_result,
                fx_orders_result,
                proj_result,
            ]
        )

        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/cashflow/payment-calendar?horizon_days=30")
        assert resp.status_code == 200
        body = resp.json()
        assert body["has_shortfall"] is False
        assert body["entries"] == []


# ---------------------------------------------------------------------------
# Triage Functions
# ---------------------------------------------------------------------------


def _make_triage(**overrides):
    defaults = dict(
        trigger_date=date.today(),
        shortfall_amount=Decimal("500000.000000"),
        horizon_days=90,
        status=TriageStatus.ACTIVE,
        resolution_date=None,
    )
    defaults.update(overrides)
    triage = TriageRecord(**defaults)
    triage.id = overrides.get("id", uuid.uuid4())
    triage.created_at = datetime.now(timezone.utc)
    triage.updated_at = datetime.now(timezone.utc)
    return triage


def _make_loan_payment_schedule(**overrides):
    defaults = dict(
        loan_id=uuid.uuid4(),
        due_date=date.today() + timedelta(days=30),
        principal_portion=Decimal("40000.000000"),
        interest_portion=Decimal("10000.000000"),
        total_payment=Decimal("50000.000000"),
        is_paid=False,
        paid_date=None,
    )
    defaults.update(overrides)
    schedule = LoanPaymentSchedule(**defaults)
    schedule.id = overrides.get("id", uuid.uuid4())
    return schedule


class TestOperatingCostDates:
    """Test _generate_operating_cost_dates helper."""

    def test_monthly_cost_dates(self):
        from src.cashflow.service import _generate_operating_cost_dates

        cost = _make_operating_cost(frequency=CostFrequency.MONTHLY)
        start = date(2026, 4, 1)
        end = date(2026, 6, 30)
        dates = _generate_operating_cost_dates(cost, start, end)
        # Monthly ~ every 30 days over ~91 days -> should get ~3-4 entries
        assert len(dates) >= 3
        for d, amount in dates:
            assert amount == cost.cost_amount

    def test_weekly_cost_dates(self):
        from src.cashflow.service import _generate_operating_cost_dates

        cost = _make_operating_cost(frequency=CostFrequency.WEEKLY)
        start = date(2026, 4, 1)
        end = date(2026, 4, 30)
        dates = _generate_operating_cost_dates(cost, start, end)
        # Weekly over 30 days -> ~4-5 entries
        assert len(dates) >= 4

    def test_quarterly_cost_dates(self):
        from src.cashflow.service import _generate_operating_cost_dates

        cost = _make_operating_cost(frequency=CostFrequency.QUARTERLY)
        start = date(2026, 4, 1)
        end = date(2026, 7, 1)
        dates = _generate_operating_cost_dates(cost, start, end)
        # Quarterly (~91 days) over 91 days -> 1 entry
        assert len(dates) >= 1


class TestTriageFunctions:
    @pytest.mark.asyncio
    async def test_get_active_triage_none(self):
        from src.cashflow.service import get_active_triage

        db = _mock_db_with_execute(scalar_result=None)
        result = await get_active_triage(db, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_active_triage_found(self):
        from src.cashflow.service import get_active_triage

        triage = _make_triage()
        db = _mock_db_with_execute(scalar_result=triage)
        result = await get_active_triage(db, uuid.uuid4())
        assert result is not None
        assert result.status == TriageStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_auto_resolve_no_active(self):
        from src.cashflow.service import auto_resolve_triage

        db = _mock_db_with_execute(scalar_result=None)
        result = await auto_resolve_triage(db, uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_auto_resolve_active(self):
        from src.cashflow.service import auto_resolve_triage

        triage = _make_triage()
        db = _mock_db_with_execute(scalar_result=triage)
        result = await auto_resolve_triage(db, uuid.uuid4())
        assert result is True
        assert triage.status == TriageStatus.RESOLVED
        assert triage.resolution_date == date.today()

    @pytest.mark.asyncio
    async def test_check_and_activate_no_shortfall(self):
        """When no shortfall exists, triage should not be activated."""
        from src.cashflow.service import check_and_activate_triage

        db = _mock_db()

        # build_payment_calendar calls: loan schedules, opex, fx_rate, fx_orders, projection
        loan_result = MagicMock()
        loan_result.all.return_value = []
        opex_result = MagicMock()
        opex_scalars = MagicMock()
        opex_scalars.all.return_value = []
        opex_result.scalars.return_value = opex_scalars
        fx_rate_result = MagicMock()
        fx_rate_result.scalar.return_value = None
        fx_orders_result = MagicMock()
        fx_orders_scalars = MagicMock()
        fx_orders_scalars.all.return_value = []
        fx_orders_result.scalars.return_value = fx_orders_scalars
        # Projection for starting balance
        proj_result = MagicMock()
        proj_result.scalar_one_or_none.return_value = None
        # auto_resolve_triage: get_active_triage
        triage_result = MagicMock()
        triage_result.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(
            side_effect=[
                loan_result,  # loan schedules
                opex_result,  # opex
                fx_rate_result,  # fx rate
                fx_orders_result,  # fx orders
                proj_result,  # projection for starting balance
                triage_result,  # get_active_triage in auto_resolve
            ]
        )

        result = await check_and_activate_triage(db, uuid.uuid4(), horizon_days=30)
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_recommendations_with_active_triage(self):
        """Test recommendation generation with an active triage."""
        from src.cashflow.service import generate_triage_recommendations

        triage = _make_triage(shortfall_amount=Decimal("200000.000000"))
        db = _mock_db()

        # Calls: get_active_triage, get_liquidation_candidates,
        # opex (deferrable), pending sales
        triage_result = MagicMock()
        triage_result.scalar_one_or_none.return_value = triage

        # Liquidation candidates
        liquidation_result = MagicMock()
        liquidation_scalars = MagicMock()
        liquidation_scalars.all.return_value = []
        liquidation_result.scalars.return_value = liquidation_scalars

        # Deferrable opex
        opex_result = MagicMock()
        opex_scalars = MagicMock()
        opex_scalars.all.return_value = []
        opex_result.scalars.return_value = opex_scalars

        # Pending sales
        pending_result = MagicMock()
        pending_result.one.return_value = (0, Decimal("0"))

        db.execute = AsyncMock(
            side_effect=[
                triage_result,  # get_active_triage
                liquidation_result,  # get_liquidation_candidates
                opex_result,  # deferrable opex
                pending_result,  # pending sales
            ]
        )

        result = await generate_triage_recommendations(db, uuid.uuid4())
        assert result["shortfall_amount"] == Decimal("200000.000000")
        assert result["triage_id"] == triage.id
        # LIQUIDATE should be present (even with empty candidates)
        action_types = [r["action_type"] for r in result["recommendations"]]
        assert "LIQUIDATE" in action_types

    @pytest.mark.asyncio
    async def test_generate_recommendations_with_pending_sales(self):
        """Test that ACCELERATE_COLLECTION appears when pending sales exist."""
        from src.cashflow.service import generate_triage_recommendations

        triage = _make_triage(shortfall_amount=Decimal("100000.000000"))
        db = _mock_db()

        triage_result = MagicMock()
        triage_result.scalar_one_or_none.return_value = triage

        liquidation_result = MagicMock()
        liquidation_scalars = MagicMock()
        liquidation_scalars.all.return_value = []
        liquidation_result.scalars.return_value = liquidation_scalars

        opex_result = MagicMock()
        opex_scalars = MagicMock()
        opex_scalars.all.return_value = []
        opex_result.scalars.return_value = opex_scalars

        pending_result = MagicMock()
        pending_result.one.return_value = (3, Decimal("150000.000000"))

        db.execute = AsyncMock(
            side_effect=[
                triage_result,
                liquidation_result,
                opex_result,
                pending_result,
            ]
        )

        result = await generate_triage_recommendations(db, uuid.uuid4())
        action_types = [r["action_type"] for r in result["recommendations"]]
        assert "ACCELERATE_COLLECTION" in action_types
        accel = next(
            r
            for r in result["recommendations"]
            if r["action_type"] == "ACCELERATE_COLLECTION"
        )
        assert accel["estimated_impact"] == Decimal("150000.000000")
        assert accel["priority"] == 3

    @pytest.mark.asyncio
    async def test_generate_recommendations_with_deferrable_costs(self):
        """Test that DELAY_PAYMENT appears when deferrable costs exist."""
        from src.cashflow.service import generate_triage_recommendations

        triage = _make_triage(shortfall_amount=Decimal("100000.000000"))
        db = _mock_db()

        triage_result = MagicMock()
        triage_result.scalar_one_or_none.return_value = triage

        liquidation_result = MagicMock()
        liquidation_scalars = MagicMock()
        liquidation_scalars.all.return_value = []
        liquidation_result.scalars.return_value = liquidation_scalars

        marketing_cost = _make_operating_cost(
            cost_name="Facebook Ads",
            category=CostCategory.MARKETING,
            monthly_equivalent=Decimal("50000.00"),
        )
        opex_result = MagicMock()
        opex_scalars = MagicMock()
        opex_scalars.all.return_value = [marketing_cost]
        opex_result.scalars.return_value = opex_scalars

        pending_result = MagicMock()
        pending_result.one.return_value = (0, Decimal("0"))

        db.execute = AsyncMock(
            side_effect=[
                triage_result,
                liquidation_result,
                opex_result,
                pending_result,
            ]
        )

        result = await generate_triage_recommendations(db, uuid.uuid4())
        action_types = [r["action_type"] for r in result["recommendations"]]
        assert "DELAY_PAYMENT" in action_types
        delay = next(
            r for r in result["recommendations"] if r["action_type"] == "DELAY_PAYMENT"
        )
        assert delay["estimated_impact"] == Decimal("50000.00")


# ---------------------------------------------------------------------------
# Business Isolation Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cashflow_projections_isolates_by_business():
    """get_latest_projection returns only record for the given business_id."""
    from src.cashflow.service import get_latest_projection

    business_a_id = uuid.uuid4()
    business_b_id = uuid.uuid4()

    proj_a = _make_projection()

    async def fake_execute_a(query):
        r = MagicMock()
        r.scalar_one_or_none.return_value = proj_a
        r.scalar.return_value = proj_a
        return r

    async def fake_execute_b(query):
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        r.scalar.return_value = None
        return r

    db_a, db_b = AsyncMock(), AsyncMock()
    db_a.execute = fake_execute_a
    db_b.execute = fake_execute_b

    result_a = await get_latest_projection(db_a, business_id=business_a_id)
    assert result_a is not None

    from src.cashflow.exceptions import ProjectionNotFoundError

    with pytest.raises(ProjectionNotFoundError):
        await get_latest_projection(db_b, business_id=business_b_id)


@pytest.mark.asyncio
async def test_operating_costs_isolates_by_business():
    """get_operating_costs returns only records for the given business_id."""
    from src.cashflow.service import get_operating_costs

    business_a_id = uuid.uuid4()
    business_b_id = uuid.uuid4()

    cost_a = _make_operating_cost()

    async def fake_execute_a(query):
        r = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [cost_a]
        r.scalars.return_value = scalars_mock
        return r

    async def fake_execute_b(query):
        r = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        r.scalars.return_value = scalars_mock
        return r

    db_a, db_b = AsyncMock(), AsyncMock()
    db_a.execute = fake_execute_a
    db_b.execute = fake_execute_b

    result_a = await get_operating_costs(db_a, business_id=business_a_id)
    result_b = await get_operating_costs(db_b, business_id=business_b_id)
    assert len(result_a) > 0
    assert len(result_b) == 0


@pytest.mark.asyncio
async def test_loan_obligations_isolates_by_business():
    """get_loans returns only records for the given business_id."""
    from src.cashflow.service import get_loans

    business_a_id = uuid.uuid4()
    business_b_id = uuid.uuid4()

    loan_a = _make_loan()

    async def fake_execute_a(query):
        r = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [loan_a]
        r.scalars.return_value = scalars_mock
        return r

    async def fake_execute_b(query):
        r = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        r.scalars.return_value = scalars_mock
        return r

    db_a, db_b = AsyncMock(), AsyncMock()
    db_a.execute = fake_execute_a
    db_b.execute = fake_execute_b

    result_a = await get_loans(db_a, business_id=business_a_id)
    result_b = await get_loans(db_b, business_id=business_b_id)
    assert len(result_a) > 0
    assert len(result_b) == 0


@pytest.mark.asyncio
async def test_triage_records_isolates_by_business():
    """get_active_triage returns only records for the given business_id."""
    from src.cashflow.service import get_active_triage

    business_a_id = uuid.uuid4()
    business_b_id = uuid.uuid4()

    triage_a = _make_triage()

    async def fake_execute_a(query):
        r = MagicMock()
        r.scalar_one_or_none.return_value = triage_a
        return r

    async def fake_execute_b(query):
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        return r

    db_a, db_b = AsyncMock(), AsyncMock()
    db_a.execute = fake_execute_a
    db_b.execute = fake_execute_b

    result_a = await get_active_triage(db_a, business_id=business_a_id)
    result_b = await get_active_triage(db_b, business_id=business_b_id)
    assert result_a is not None
    assert result_b is None


# ---------------------------------------------------------------------------
# Bug-fix isolation tests: helper functions scoped to business_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calculate_monthly_revenue_accepts_business_id():
    """_calculate_monthly_revenue must accept and use business_id parameter."""
    from src.cashflow.service import _calculate_monthly_revenue

    business_id = uuid.uuid4()
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar.return_value = Decimal("3000000")
    db.execute = AsyncMock(return_value=result_mock)

    revenue = await _calculate_monthly_revenue(db, business_id)
    assert revenue == Decimal("1000000.00")  # 3M / 3 months


@pytest.mark.asyncio
async def test_calculate_monthly_revenue_no_cross_tenant_data():
    """_calculate_monthly_revenue with business_id=B should return 0 when no sales."""
    from src.cashflow.service import _calculate_monthly_revenue

    business_b_id = uuid.uuid4()
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar.return_value = None  # no sales for this business
    db.execute = AsyncMock(return_value=result_mock)

    revenue = await _calculate_monthly_revenue(db, business_b_id)
    assert revenue == Decimal("0.00")


@pytest.mark.asyncio
async def test_sum_open_order_usd_obligations_accepts_business_id():
    """_sum_open_order_usd_obligations must accept and use business_id parameter."""
    from src.cashflow.service import _sum_open_order_usd_obligations

    business_id = uuid.uuid4()
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar.return_value = Decimal("50000")
    db.execute = AsyncMock(return_value=result_mock)

    obligations = await _sum_open_order_usd_obligations(db, business_id)
    assert obligations == Decimal("50000")


@pytest.mark.asyncio
async def test_sum_open_order_usd_obligations_zero_for_unknown_business():
    """_sum_open_order_usd_obligations returns 0 for a business with no orders."""
    from src.cashflow.service import _sum_open_order_usd_obligations

    business_id = uuid.uuid4()
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar.return_value = None
    db.execute = AsyncMock(return_value=result_mock)

    obligations = await _sum_open_order_usd_obligations(db, business_id)
    assert obligations == Decimal("0")


@pytest.mark.asyncio
async def test_trailing_30d_avg_monthly_revenue_accepts_business_id():
    """_trailing_30d_avg_monthly_revenue_usd must accept and use business_id parameter."""
    from src.cashflow.service import _trailing_30d_avg_monthly_revenue_usd

    business_id = uuid.uuid4()
    ngn_usd_rate = Decimal("1500")
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar.return_value = Decimal("1500000")  # 1500 NGN/USD * 1000 USD
    db.execute = AsyncMock(return_value=result_mock)

    revenue_usd = await _trailing_30d_avg_monthly_revenue_usd(
        db, business_id, ngn_usd_rate
    )
    assert revenue_usd == Decimal("1000.00")  # 1500000 NGN / 1500


@pytest.mark.asyncio
async def test_trailing_30d_avg_monthly_revenue_zero_for_unknown_business():
    """_trailing_30d_avg_monthly_revenue_usd returns 0 for business with no sales."""
    from src.cashflow.service import _trailing_30d_avg_monthly_revenue_usd

    business_id = uuid.uuid4()
    ngn_usd_rate = Decimal("1500")
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar.return_value = None
    db.execute = AsyncMock(return_value=result_mock)

    revenue_usd = await _trailing_30d_avg_monthly_revenue_usd(
        db, business_id, ngn_usd_rate
    )
    assert revenue_usd == Decimal("0")


@pytest.mark.asyncio
async def test_get_scenarios_accepts_business_id():
    """get_scenarios must accept and filter by business_id."""
    from src.cashflow.service import get_scenarios

    business_id = uuid.uuid4()
    db = AsyncMock()
    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock.scalars.return_value = scalars_mock
    db.execute = AsyncMock(return_value=result_mock)

    scenarios = await get_scenarios(db, business_id)
    assert scenarios == []


@pytest.mark.asyncio
async def test_get_scenarios_flags_undefined_dscr_and_runway_as_not_finite():
    """A debt-free/no-burn saved scenario must report *_is_finite=False so the
    UI never renders the raw 999 sentinel (mirrors the live-projection fix)."""
    from src.cashflow.models import StressScenario
    from src.cashflow.service import get_scenarios

    business_id = uuid.uuid4()
    debt_free = StressScenario(
        id=uuid.uuid4(),
        business_id=business_id,
        name="FX_SHOCK_10",
        revenue_shock_pct=Decimal("0.00"),
        fx_shock_pct=Decimal("10.00"),
        cost_shock_pct=Decimal("0.00"),
        base_projection_id=uuid.uuid4(),
        stressed_dscr=Decimal("999.000"),
        stressed_runway_months=999,
        created_by=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
    )
    with_debt = StressScenario(
        id=uuid.uuid4(),
        business_id=business_id,
        name="BASE",
        revenue_shock_pct=Decimal("0.00"),
        fx_shock_pct=Decimal("0.00"),
        cost_shock_pct=Decimal("0.00"),
        base_projection_id=uuid.uuid4(),
        stressed_dscr=Decimal("2.500"),
        stressed_runway_months=6,
        created_by=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
    )

    db = AsyncMock()
    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [debt_free, with_debt]
    result_mock.scalars.return_value = scalars_mock
    db.execute = AsyncMock(return_value=result_mock)

    scenarios = await get_scenarios(db, business_id)

    assert scenarios[0]["stressed_dscr_is_finite"] is False
    assert scenarios[0]["stressed_runway_is_finite"] is False
    assert scenarios[1]["stressed_dscr_is_finite"] is True
    assert scenarios[1]["stressed_runway_is_finite"] is True
