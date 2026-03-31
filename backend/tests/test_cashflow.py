"""Tests for cashflow domain: projections, DSCR, runway, stress scenarios."""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.auth.service import build_token
from src.cashflow.exceptions import LoanNotFoundError, ProjectionNotFoundError
from src.cashflow.models import (
    CashflowProjection,
    CostCategory,
    CostFrequency,
    LoanObligation,
    LoanStatus,
    OperatingCost,
    PaymentFrequency,
)
from src.core.security import get_password_hash

VALID_PASSWORD = "Str0ng!Pass#99"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(**overrides):
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

        result = await create_loan(db, LoanData(), uuid.uuid4())
        assert result.lender_name == "Access Bank"
        assert result.outstanding_balance == Decimal("500000")
        assert db.add.called

    @pytest.mark.asyncio
    async def test_get_loans(self):
        from src.cashflow.service import get_loans

        loans = [_make_loan()]
        db = _mock_db_with_execute(scalars_result=loans)
        result = await get_loans(db)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_loan_not_found(self):
        from src.cashflow.service import get_loan

        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(LoanNotFoundError):
            await get_loan(db, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_loan_success(self):
        from src.cashflow.service import get_loan

        loan = _make_loan()
        db = _mock_db_with_execute(scalar_result=loan)
        result = await get_loan(db, loan.id)
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

        result = await create_operating_cost(db, CostData(), uuid.uuid4())
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

        result = await create_operating_cost(db, CostData(), uuid.uuid4())
        assert result.monthly_equivalent == Decimal("21650.00")

    @pytest.mark.asyncio
    async def test_get_operating_costs(self):
        from src.cashflow.service import get_operating_costs

        costs = [_make_operating_cost()]
        db = _mock_db_with_execute(scalars_result=costs)
        result = await get_operating_costs(db)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# DSCR Calculation
# ---------------------------------------------------------------------------


class TestDSCR:
    def test_dscr_healthy(self):
        from src.cashflow.service import _calculate_dscr

        dscr = _calculate_dscr(
            Decimal("1000000"), Decimal("600000"), Decimal("200000")
        )
        assert dscr == Decimal("2.000")

    def test_dscr_no_debt(self):
        from src.cashflow.service import _calculate_dscr

        dscr = _calculate_dscr(Decimal("1000000"), Decimal("600000"), Decimal("0"))
        assert dscr == Decimal("999.000")

    def test_dscr_below_1(self):
        from src.cashflow.service import _calculate_dscr

        dscr = _calculate_dscr(
            Decimal("500000"), Decimal("400000"), Decimal("200000")
        )
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

        result = await get_current_dscr(db)
        assert result["dscr"] == Decimal("3.500")  # (1M - 300k) / 200k
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


class TestCashRunway:
    @pytest.mark.asyncio
    async def test_runway_no_projection(self):
        from src.cashflow.service import calculate_cash_runway

        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(ProjectionNotFoundError):
            await calculate_cash_runway(db)

    @pytest.mark.asyncio
    async def test_runway_all_positive(self):
        from src.cashflow.service import calculate_cash_runway

        proj = _make_projection()
        db = _mock_db_with_execute(scalar_result=proj)
        result = await calculate_cash_runway(db)
        assert result["runway_months"] == Decimal("999.0")
        assert result["avg_monthly_burn"] == Decimal("0")

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
        result = await calculate_cash_runway(db)
        assert result["runway_months"] == Decimal("3.0")
        assert result["avg_monthly_burn"] == Decimal("-100000.00")


# ---------------------------------------------------------------------------
# Liquidity Alerts
# ---------------------------------------------------------------------------


class TestLiquidityAlerts:
    @pytest.mark.asyncio
    async def test_no_projection_no_alerts(self):
        from src.cashflow.service import check_liquidity_alerts

        db = _mock_db_with_execute(scalar_result=None)
        result = await check_liquidity_alerts(db)
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
        result = await check_liquidity_alerts(db)
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
        result = await check_liquidity_alerts(db)
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

    def test_avg_runway_from_buckets(self):
        from src.cashflow.service import _avg_runway_from_buckets

        buckets = [{"cash_runway_months": "6.0"}, {"cash_runway_months": "4.0"}]
        assert _avg_runway_from_buckets(buckets) == 5

    def test_summarize_projection(self):
        from src.cashflow.service import _summarize_projection

        proj = _make_projection()
        summary = _summarize_projection(proj)
        assert summary["risk_rating"] == "LOW"
        assert summary["avg_dscr"] == 8.0
        assert "net_cashflow" in summary


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

    def test_list_loans_empty(self):
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
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/cashflow/loans/{fake_id}")
        assert resp.status_code == 404

    def test_list_operating_costs_empty(self):
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
        db = _mock_db_with_execute(scalars_result=[])
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/cashflow/scenarios")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_alerts_empty(self):
        # No projection found -> returns empty alerts
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/cashflow/alerts")
        assert resp.status_code == 200
        assert resp.json() == []
