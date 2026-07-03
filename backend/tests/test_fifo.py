"""Tests for batch FIFO inventory tracking (Task 18)."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.inventory.models import InventoryBatch, InventoryLevel
from src.inventory.service import (
    compute_landed_cost,
    create_batch,
    fifo_deduct,
    get_batches_for_product,
    get_liquidation_candidates,
)
from src.sales.models import SaleStatus
from src.sales.schemas import SaleCreate
from src.sales.service import create_sale


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_batch(
    quantity_received=100,
    quantity_remaining=100,
    unit_cost_usd=Decimal("10"),
    fx_rate=Decimal("1500"),
    logistics=Decimal("50"),
    received_at=None,
    product_id=None,
):
    batch = InventoryBatch(
        product_id=product_id or uuid.uuid4(),
        order_id=uuid.uuid4(),
        quantity_received=quantity_received,
        quantity_remaining=quantity_remaining,
        unit_cost_usd=unit_cost_usd,
        fx_rate_at_arrival=fx_rate,
        logistics_allocation_per_unit=logistics,
        landed_cost_per_unit=compute_landed_cost(unit_cost_usd, fx_rate, logistics),
        received_at=received_at or date.today(),
        created_at=datetime.now(timezone.utc),
    )
    batch.id = uuid.uuid4()
    return batch


# ---------------------------------------------------------------------------
# Landed cost calculation
# ---------------------------------------------------------------------------


class TestLandedCost:
    def test_basic_calculation(self):
        """landed_cost = (unit_cost × fx_rate) + logistics."""
        result = compute_landed_cost(
            Decimal("10"), Decimal("1500"), Decimal("50")
        )
        assert result == Decimal("15050.000000")

    def test_zero_logistics(self):
        result = compute_landed_cost(
            Decimal("10"), Decimal("1500"), Decimal("0")
        )
        assert result == Decimal("15000.000000")

    def test_decimal_precision(self):
        result = compute_landed_cost(
            Decimal("9.99"), Decimal("1501.50"), Decimal("33.33")
        )
        expected = (Decimal("9.99") * Decimal("1501.50") + Decimal("33.33")).quantize(
            Decimal("0.000001")
        )
        assert result == expected


# ---------------------------------------------------------------------------
# Batch creation
# ---------------------------------------------------------------------------


class TestCreateBatch:
    @pytest.mark.asyncio
    async def test_create_batch(self):
        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        batch = await create_batch(
            db,
            product_id=uuid.uuid4(),
            order_id=uuid.uuid4(),
            quantity=50,
            unit_cost_usd=Decimal("10"),
            fx_rate_at_arrival=Decimal("1500"),
            logistics_allocation_per_unit=Decimal("100"),
        )

        assert batch.quantity_received == 50
        assert batch.quantity_remaining == 50
        assert batch.landed_cost_per_unit == Decimal("15100.000000")
        db.add.assert_called_once()


# ---------------------------------------------------------------------------
# FIFO deduction
# ---------------------------------------------------------------------------


class TestFifoDeduct:
    @pytest.mark.asyncio
    async def test_single_batch_full_deduct(self):
        """Sale fits entirely within one batch."""
        product_id = uuid.uuid4()
        batch = _make_batch(
            quantity_remaining=100,
            unit_cost_usd=Decimal("10"),
            fx_rate=Decimal("1500"),
            logistics=Decimal("0"),
            product_id=product_id,
        )

        db = AsyncMock()
        db.flush = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [batch]
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        cogs = await fifo_deduct(db, product_id, 30)

        assert cogs == Decimal(30) * Decimal("15000")
        assert batch.quantity_remaining == 70

    @pytest.mark.asyncio
    async def test_spans_two_batches(self):
        """Sale spans two batches with different costs — FIFO order."""
        product_id = uuid.uuid4()
        batch1 = _make_batch(
            quantity_remaining=10,
            unit_cost_usd=Decimal("10"),
            fx_rate=Decimal("1500"),
            logistics=Decimal("0"),
            product_id=product_id,
        )
        batch2 = _make_batch(
            quantity_remaining=20,
            unit_cost_usd=Decimal("12"),
            fx_rate=Decimal("1600"),
            logistics=Decimal("0"),
            product_id=product_id,
        )

        db = AsyncMock()
        db.flush = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [batch1, batch2]
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        cogs = await fifo_deduct(db, product_id, 15)

        # batch1: 10 units × 15000 = 150000
        # batch2: 5 units × 19200 = 96000
        expected = Decimal("10") * Decimal("15000") + Decimal("5") * Decimal("19200")
        assert cogs == expected
        assert batch1.quantity_remaining == 0
        assert batch2.quantity_remaining == 15

    @pytest.mark.asyncio
    async def test_no_batches_available(self):
        """Sale with no batches returns 0 COGS."""
        db = AsyncMock()
        db.flush = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        cogs = await fifo_deduct(db, uuid.uuid4(), 10)
        assert cogs == Decimal("0")


# ---------------------------------------------------------------------------
# Liquidation candidates
# ---------------------------------------------------------------------------


class TestLiquidationCandidates:
    @pytest.mark.asyncio
    async def test_returns_cheapest_first(self):
        cheap = _make_batch(
            quantity_remaining=50,
            unit_cost_usd=Decimal("5"),
            fx_rate=Decimal("1500"),
            logistics=Decimal("0"),
        )
        expensive = _make_batch(
            quantity_remaining=50,
            unit_cost_usd=Decimal("20"),
            fx_rate=Decimal("1500"),
            logistics=Decimal("0"),
        )

        db = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [cheap, expensive]
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        candidates = await get_liquidation_candidates(db, Decimal("500000"))

        assert len(candidates) == 2
        assert candidates[0]["landed_cost_per_unit"] < candidates[1]["landed_cost_per_unit"]

    @pytest.mark.asyncio
    async def test_empty_batches(self):
        db = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        candidates = await get_liquidation_candidates(db, Decimal("500000"))
        assert candidates == []


# ---------------------------------------------------------------------------
# FIFO wired to create_sale
# ---------------------------------------------------------------------------


class TestFifoWiredToSale:
    @pytest.mark.asyncio
    async def test_create_sale_sets_fifo_fields(self):
        """create_sale should call fifo_deduct and set fifo_cogs / fifo_gross_profit."""
        from src.products.models import Product

        product_id = uuid.uuid4()
        product = Product(
            name="Widget",
            sku="WGT-001",
            description="A widget",
            category_id=uuid.uuid4(),
            unit_cost=Decimal("100"),
            selling_price=Decimal("200"),
            currency="NGN",
            is_active=True,
        )
        product.id = product_id
        product.created_at = datetime.now(timezone.utc)
        product.updated_at = datetime.now(timezone.utc)

        inventory = InventoryLevel(
            product_id=product_id,
            quantity_on_hand=50,
            quantity_reserved=0,
            low_stock_threshold=5,
        )
        inventory.id = uuid.uuid4()
        inventory.created_at = datetime.now(timezone.utc)
        inventory.updated_at = datetime.now(timezone.utc)

        batch = _make_batch(
            quantity_remaining=50,
            unit_cost_usd=Decimal("10"),
            fx_rate=Decimal("1500"),
            logistics=Decimal("0"),
            product_id=product_id,
        )

        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Product lookup
                result.scalar_one_or_none.return_value = product
            elif call_count == 2:
                # get_inventory_level (inside adjust_stock)
                result.scalar_one_or_none.return_value = inventory
            elif call_count == 3:
                # fifo_deduct batch query
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = [batch]
                result.scalars.return_value = scalars_mock
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        data = SaleCreate(
            product_id=product_id,
            quantity=5,
            unit_price=Decimal("200"),
            sale_date=date(2026, 3, 15),
            channel="retail",
        )
        sale = await create_sale(db, data, uuid.uuid4(), business_id=uuid.uuid4())

        # 5 units × 15000.000000 landed cost = 75000.000000
        expected_cogs = Decimal("75000.000000")
        expected_profit = Decimal("1000") - expected_cogs  # total_amount=1000

        assert sale.fifo_cogs == expected_cogs
        assert sale.fifo_gross_profit == expected_profit
        assert batch.quantity_remaining == 45
