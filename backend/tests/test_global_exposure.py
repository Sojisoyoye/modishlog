"""Tests for multi-currency global exposure (Task 16)."""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.cashflow.models import LoanObligation, LoanStatus
from src.cashflow.service import (
    EUR_USD_ALERT_THRESHOLD_PCT,
    calculate_global_exposure,
    check_eur_usd_alert,
)
from src.fx.service import get_cross_rate, get_latest_rate_value, get_previous_rate_value


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_db(execute_side_effects=None):
    """Build an AsyncMock db with configurable execute returns."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    if execute_side_effects:
        db.execute = AsyncMock(side_effect=execute_side_effects)
    return db


def _scalar_result(value):
    """Build a mock result where .scalar() returns value."""
    result = MagicMock()
    result.scalar.return_value = value
    result.scalar_one_or_none.return_value = value
    return result


def _rows_result(rows):
    """Build a mock result where .all() returns rows."""
    result = MagicMock()
    result.all.return_value = rows
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = rows
    result.scalars.return_value = scalars_mock
    return result


# ---------------------------------------------------------------------------
# FX Cross-Rate Tests
# ---------------------------------------------------------------------------


class TestCrossRate:
    @pytest.mark.asyncio
    async def test_get_latest_rate_value_found(self):
        db = AsyncMock()
        result = _scalar_result(Decimal("1500.000000"))
        db.execute = AsyncMock(return_value=result)

        rate = await get_latest_rate_value(db, "USDNGN")
        assert rate == Decimal("1500.000000")

    @pytest.mark.asyncio
    async def test_get_latest_rate_value_not_found(self):
        db = AsyncMock()
        result = _scalar_result(None)
        db.execute = AsyncMock(return_value=result)

        rate = await get_latest_rate_value(db, "XXXYYY")
        assert rate is None

    @pytest.mark.asyncio
    async def test_get_cross_rate(self):
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _scalar_result(Decimal("1.080000"))  # EURUSD
            return _scalar_result(Decimal("1500.000000"))  # USDNGN

        db = AsyncMock()
        db.execute = mock_execute

        cross = await get_cross_rate(db, "EURUSD", "USDNGN")
        assert cross == Decimal("1.080000") * Decimal("1500.000000")

    @pytest.mark.asyncio
    async def test_get_cross_rate_missing_pair(self):
        db = AsyncMock()
        result = _scalar_result(None)
        db.execute = AsyncMock(return_value=result)

        cross = await get_cross_rate(db, "EURUSD", "USDNGN")
        assert cross is None

    @pytest.mark.asyncio
    async def test_get_previous_rate_value(self):
        db = AsyncMock()
        result = _scalar_result(Decimal("1.070000"))
        db.execute = AsyncMock(return_value=result)

        prev = await get_previous_rate_value(db, "EURUSD")
        assert prev == Decimal("1.070000")


# ---------------------------------------------------------------------------
# Global Exposure Calculation Tests
# ---------------------------------------------------------------------------


class TestGlobalExposure:
    @pytest.mark.asyncio
    async def test_global_exposure_with_known_rates(self):
        """Verify formula: total_ngn = (usd × ngn_usd) + (eur × eur_usd × ngn_usd)."""
        eur_balance = Decimal("50000")
        usd_obligations = Decimal("0")
        eur_usd = Decimal("1.100000")
        ngn_usd = Decimal("1500.000000")

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            # Calls in order:
            # 1: get_latest_rate_value USDNGN
            # 2: get_latest_rate_value EURUSD
            # 3: sum(current_balance) for EUR loans
            # 4: _sum_open_order_usd_obligations (single aggregate)
            # 5: trailing revenue
            if call_count == 1:
                return _scalar_result(ngn_usd)
            if call_count == 2:
                return _scalar_result(eur_usd)
            if call_count == 3:
                return _scalar_result(eur_balance)
            if call_count == 4:
                return _scalar_result(Decimal("0"))  # no open USD orders
            # trailing revenue query
            return _scalar_result(Decimal("0"))

        db = _make_mock_db()
        db.execute = mock_execute

        result = await calculate_global_exposure(db)

        expected_total = (
            usd_obligations * ngn_usd + eur_balance * eur_usd * ngn_usd
        ).quantize(Decimal("0.01"))

        assert result["eur_loan_balance_eur"] == eur_balance
        assert result["eur_usd_rate"] == eur_usd
        assert result["eur_usd_rate_available"] is True
        assert result["ngn_usd_rate"] == ngn_usd
        assert result["open_order_usd_obligations"] == usd_obligations
        assert result["total_global_exposure_ngn"] == expected_total

    @pytest.mark.asyncio
    async def test_debt_to_trade_ratio_zero_revenue(self):
        """If no revenue, debt_to_trade_ratio should be 0."""
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _scalar_result(Decimal("1500"))  # USDNGN
            if call_count == 2:
                return _scalar_result(Decimal("1.08"))  # EURUSD
            if call_count == 3:
                return _scalar_result(Decimal("10000"))  # EUR balance
            if call_count == 4:
                return _scalar_result(Decimal("0"))  # no open USD orders
            return _scalar_result(Decimal("0"))  # zero revenue

        db = _make_mock_db()
        db.execute = mock_execute

        result = await calculate_global_exposure(db)
        assert result["debt_to_trade_ratio"] == Decimal("0")


# ---------------------------------------------------------------------------
# EUR/USD Alert Tests
# ---------------------------------------------------------------------------


class TestEurUsdAlert:
    @pytest.mark.asyncio
    async def test_no_alert_below_threshold(self):
        """Small rate change should not trigger alert."""
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _scalar_result(Decimal("1.081"))  # current
            return _scalar_result(Decimal("1.080"))  # previous

        db = _make_mock_db()
        db.execute = mock_execute

        triggered = await check_eur_usd_alert(db)
        assert triggered is False

    @pytest.mark.asyncio
    async def test_alert_above_threshold(self):
        """Large rate change should trigger alert and create recommendation."""
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _scalar_result(Decimal("1.150"))  # current (big jump)
            if call_count == 2:
                return _scalar_result(Decimal("1.080"))  # previous
            if call_count == 3:
                return _scalar_result(0)  # dedup count: no existing alert
            return _scalar_result(None)

        db = _make_mock_db()
        db.execute = mock_execute

        triggered = await check_eur_usd_alert(db)
        assert triggered is True
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_alert_dedup_skips_duplicate(self):
        """If a pending EURUSD alert already exists, skip creating another."""
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _scalar_result(Decimal("1.150"))  # current
            if call_count == 2:
                return _scalar_result(Decimal("1.080"))  # previous
            if call_count == 3:
                return _scalar_result(1)  # dedup count: existing alert found
            return _scalar_result(None)

        db = _make_mock_db()
        db.execute = mock_execute

        triggered = await check_eur_usd_alert(db)
        assert triggered is False
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_alert_missing_rates(self):
        """No previous rate means no alert."""
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _scalar_result(Decimal("1.08"))
            return _scalar_result(None)

        db = _make_mock_db()
        db.execute = mock_execute

        triggered = await check_eur_usd_alert(db)
        assert triggered is False
