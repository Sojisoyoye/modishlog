"""Tests for logistics efficiency tracker (Task 17)."""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.orders.models import OrderStatus, PurchaseOrder
from src.orders.service import (
    LOGISTICS_AMBER_THRESHOLD,
    LOGISTICS_RED_THRESHOLD,
    calculate_logistics_pct,
    check_logistics_alerts,
    get_logistics_efficiency,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scalar_result(value):
    result = MagicMock()
    result.scalar.return_value = value
    result.scalar_one_or_none.return_value = value
    return result


def _make_order(
    shipping_cost=Decimal("0"),
    clearing_cost=Decimal("0"),
    total_amount=Decimal("10000"),
    status=OrderStatus.DELIVERED,
):
    order = PurchaseOrder(
        order_number=f"PO-{uuid.uuid4().hex[:6]}",
        supplier_name="Test Supplier",
        status=status,
        total_amount=total_amount,
        currency="USD",
        shipping_cost=shipping_cost,
        clearing_cost=clearing_cost,
        created_by=uuid.uuid4(),
    )
    order.id = uuid.uuid4()
    order.created_at = datetime.now(timezone.utc)
    order.updated_at = datetime.now(timezone.utc)
    order.line_items = []
    return order


# ---------------------------------------------------------------------------
# Pure calculation tests
# ---------------------------------------------------------------------------


class TestLogisticsPctCalculation:
    def test_normal_calculation(self):
        """logistics_pct = (shipping + clearing) / cogs × 100"""
        result = calculate_logistics_pct(
            Decimal("500"), Decimal("300"), Decimal("10000")
        )
        assert result == Decimal("8.00")

    def test_zero_cogs(self):
        """Zero COGS should return 0, not divide by zero."""
        result = calculate_logistics_pct(
            Decimal("500"), Decimal("300"), Decimal("0")
        )
        assert result == Decimal("0")

    def test_zero_costs(self):
        """No logistics costs should return 0%."""
        result = calculate_logistics_pct(
            Decimal("0"), Decimal("0"), Decimal("10000")
        )
        assert result == Decimal("0.00")

    def test_high_logistics(self):
        """25% logistics costs."""
        result = calculate_logistics_pct(
            Decimal("1500"), Decimal("1000"), Decimal("10000")
        )
        assert result == Decimal("25.00")

    def test_threshold_boundaries(self):
        """Exactly at amber threshold."""
        result = calculate_logistics_pct(
            Decimal("1000"), Decimal("500"), Decimal("10000")
        )
        assert result == Decimal("15.00")
        assert result == LOGISTICS_AMBER_THRESHOLD


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


class TestGetLogisticsEfficiency:
    @pytest.mark.asyncio
    async def test_healthy_status(self):
        """Orders with low logistics should return healthy."""
        orders = [
            _make_order(shipping_cost=Decimal("200"), clearing_cost=Decimal("100")),
            _make_order(shipping_cost=Decimal("300"), clearing_cost=Decimal("150")),
        ]

        db = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = orders
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        data = await get_logistics_efficiency(db)

        assert data["status"] == "healthy"
        assert len(data["per_order"]) == 2
        assert data["rolling_90d_avg_pct"] < LOGISTICS_AMBER_THRESHOLD

    @pytest.mark.asyncio
    async def test_amber_status(self):
        """Orders with logistics > 15% should return amber."""
        orders = [
            _make_order(
                shipping_cost=Decimal("1200"),
                clearing_cost=Decimal("600"),
                total_amount=Decimal("10000"),
            ),
        ]

        db = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = orders
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        data = await get_logistics_efficiency(db)

        assert data["status"] == "amber"
        assert data["rolling_90d_avg_pct"] == Decimal("18.00")

    @pytest.mark.asyncio
    async def test_red_status(self):
        """Orders with logistics > 20% should return red."""
        orders = [
            _make_order(
                shipping_cost=Decimal("1500"),
                clearing_cost=Decimal("1000"),
                total_amount=Decimal("10000"),
            ),
        ]

        db = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = orders
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        data = await get_logistics_efficiency(db)

        assert data["status"] == "red"
        assert data["rolling_90d_avg_pct"] > LOGISTICS_RED_THRESHOLD

    @pytest.mark.asyncio
    async def test_empty_orders(self):
        """No orders should return healthy with 0%."""
        db = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        data = await get_logistics_efficiency(db)

        assert data["status"] == "healthy"
        assert data["rolling_90d_avg_pct"] == Decimal("0")
        assert len(data["per_order"]) == 0


# ---------------------------------------------------------------------------
# Alert tests
# ---------------------------------------------------------------------------


class TestLogisticsAlerts:
    @pytest.mark.asyncio
    async def test_no_alert_below_threshold(self):
        """No alert when logistics is healthy."""
        orders = [
            _make_order(shipping_cost=Decimal("200"), clearing_cost=Decimal("100")),
        ]

        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = orders
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        triggered = await check_logistics_alerts(db)
        assert triggered is False
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_alert_at_amber(self):
        """Alert triggered when > 15%."""
        orders = [
            _make_order(
                shipping_cost=Decimal("1200"),
                clearing_cost=Decimal("600"),
                total_amount=Decimal("10000"),
            ),
        ]

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # get_logistics_efficiency query
                result_mock = MagicMock()
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = orders
                result_mock.scalars.return_value = scalars_mock
                return result_mock
            # Dedup count query
            return _scalar_result(0)

        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        db.execute = mock_execute

        triggered = await check_logistics_alerts(db)
        assert triggered is True
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_alert_dedup(self):
        """Skip if pending alert already exists."""
        orders = [
            _make_order(
                shipping_cost=Decimal("1200"),
                clearing_cost=Decimal("600"),
                total_amount=Decimal("10000"),
            ),
        ]

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                result_mock = MagicMock()
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = orders
                result_mock.scalars.return_value = scalars_mock
                return result_mock
            # Dedup count returns 1 (existing alert)
            return _scalar_result(1)

        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        db.execute = mock_execute

        triggered = await check_logistics_alerts(db)
        assert triggered is False
        db.add.assert_not_called()
