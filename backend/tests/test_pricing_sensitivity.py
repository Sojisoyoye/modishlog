"""Tests for price-FX sensitivity playground (Task 20)."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.pricing.service import (
    MAX_SAVED_SCENARIOS,
    get_selling_price_suggestion,
    list_scenarios,
    save_scenario,
    sensitivity_calc,
)
from src.pricing.models import PricingScenario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_batch(unit_cost_usd, quantity_remaining=10):
    """Build a minimal InventoryBatch-like object."""
    batch = MagicMock()
    batch.unit_cost_usd = Decimal(str(unit_cost_usd))
    batch.quantity_remaining = quantity_remaining
    batch.landed_cost_per_unit = Decimal(str(unit_cost_usd)) * Decimal("750")
    return batch


def _make_product(unit_cost=Decimal("50.000000")):
    from src.products.models import Product
    product = MagicMock(spec=Product)
    product.unit_cost = unit_cost
    product.selling_price = Decimal("60000.000000")
    product.id = uuid.uuid4()
    return product


def _mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Sensitivity calc tests
# ---------------------------------------------------------------------------


class TestSensitivityCalc:
    @pytest.mark.asyncio
    async def test_calc_with_unit_cost_override(self):
        """Sensitivity calc with explicit unit_cost_usd (no product lookup)."""
        db = _mock_db()

        result = await sensitivity_calc(
            db,
            selling_price=Decimal("60000"),
            fx_rate=Decimal("750"),
            quantity=10,
            product_id=None,
            unit_cost_usd_override=Decimal("50"),
        )

        # landed_cost_ngn = 50 * 750 = 37500
        assert result["landed_cost_ngn"] == Decimal("37500.000000")
        # margin_pct = (60000 - 37500) / 60000 * 100 = 37.50
        assert result["margin_pct"] == Decimal("37.50")
        # total_revenue = 60000 * 10 = 600000
        assert result["total_revenue"] == Decimal("600000")
        # total_cost = 37500 * 10 = 375000
        assert result["total_cost"] == Decimal("375000.000000")
        # gross_profit = 600000 - 375000 = 225000
        assert result["gross_profit"] == Decimal("225000.000000")
        assert result["unit_cost_usd"] == Decimal("50")
        assert result["quantity"] == 10

    @pytest.mark.asyncio
    async def test_calc_with_product_batches(self):
        """Sensitivity calc using FIFO batches from a product."""
        db = _mock_db()
        product_id = uuid.uuid4()
        batch = _make_batch("40")

        with patch(
            "src.inventory.service.get_batches_for_product",
            new_callable=AsyncMock,
            return_value=[batch],
        ):
            result = await sensitivity_calc(
                db,
                selling_price=Decimal("50000"),
                fx_rate=Decimal("800"),
                quantity=5,
                product_id=product_id,
            )

        # unit_cost_usd from batch = 40
        assert result["unit_cost_usd"] == Decimal("40")
        # landed_cost_ngn = 40 * 800 = 32000
        assert result["landed_cost_ngn"] == Decimal("32000.000000")
        # margin_pct = (50000 - 32000) / 50000 * 100 = 36.00
        assert result["margin_pct"] == Decimal("36.00")
        # total_revenue = 50000 * 5 = 250000
        assert result["total_revenue"] == Decimal("250000")
        # total_cost = 32000 * 5 = 160000
        assert result["total_cost"] == Decimal("160000.000000")
        # gross_profit = 250000 - 160000 = 90000
        assert result["gross_profit"] == Decimal("90000.000000")

    @pytest.mark.asyncio
    async def test_calc_product_no_batches_falls_back(self):
        """Falls back to product.unit_cost when no active batches."""
        db = _mock_db()
        product_id = uuid.uuid4()
        product = _make_product(unit_cost=Decimal("60.000000"))

        with patch(
            "src.inventory.service.get_batches_for_product",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "src.pricing.service._get_product",
            new_callable=AsyncMock,
            return_value=product,
        ):
            result = await sensitivity_calc(
                db,
                selling_price=Decimal("70000"),
                fx_rate=Decimal("700"),
                quantity=1,
                product_id=product_id,
            )

        assert result["unit_cost_usd"] == Decimal("60.000000")
        # landed = 60 * 700 = 42000
        assert result["landed_cost_ngn"] == Decimal("42000.000000")

    @pytest.mark.asyncio
    async def test_calc_no_product_no_cost_raises(self):
        """Raises ValueError when neither product_id nor unit_cost_usd given."""
        db = _mock_db()

        with pytest.raises(ValueError, match="Either product_id or unit_cost_usd"):
            await sensitivity_calc(
                db,
                selling_price=Decimal("5000"),
                fx_rate=Decimal("750"),
                quantity=1,
            )

    @pytest.mark.asyncio
    async def test_calc_override_takes_precedence(self):
        """unit_cost_usd_override takes precedence over batch cost."""
        db = _mock_db()
        product_id = uuid.uuid4()
        batch = _make_batch("40")

        with patch(
            "src.inventory.service.get_batches_for_product",
            new_callable=AsyncMock,
            return_value=[batch],
        ):
            result = await sensitivity_calc(
                db,
                selling_price=Decimal("50000"),
                fx_rate=Decimal("800"),
                quantity=1,
                product_id=product_id,
                unit_cost_usd_override=Decimal("55"),
            )

        # Override should take precedence
        assert result["unit_cost_usd"] == Decimal("55")
        assert result["landed_cost_ngn"] == Decimal("44000.000000")


# ---------------------------------------------------------------------------
# Scenario save + max 10 archive tests
# ---------------------------------------------------------------------------


class TestScenarioSave:
    @pytest.mark.asyncio
    async def test_save_scenario_basic(self):
        """Save a scenario when under the limit."""
        db = _mock_db()

        # Mock count query returns 0
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        db.execute = AsyncMock(return_value=count_result)

        scenario = await save_scenario(
            db,
            name="Test Scenario",
            user_id=uuid.uuid4(),
            business_id=uuid.uuid4(),
            selling_price=Decimal("50000"),
            fx_rate=Decimal("750"),
            quantity=10,
            results={"margin_pct": "25.00"},
        )

        assert scenario.name == "Test Scenario"
        assert scenario.selling_price == Decimal("50000")
        assert scenario.fx_rate == Decimal("750")
        assert scenario.quantity == 10
        assert scenario.results == {"margin_pct": "25.00"}
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_scenario_archives_oldest_at_max(self):
        """When at max capacity, oldest scenario is deleted."""
        db = _mock_db()

        old_scenario = MagicMock(spec=PricingScenario)
        old_scenario.id = uuid.uuid4()

        # First call: count query returns MAX_SAVED_SCENARIOS
        count_result = MagicMock()
        count_result.scalar.return_value = MAX_SAVED_SCENARIOS

        # Second call: oldest scenarios query returns 1 scenario
        oldest_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [old_scenario]
        oldest_result.scalars.return_value = scalars_mock

        db.execute = AsyncMock(side_effect=[count_result, oldest_result])

        scenario = await save_scenario(
            db,
            name="New Scenario",
            user_id=uuid.uuid4(),
            business_id=uuid.uuid4(),
            selling_price=Decimal("45000"),
            fx_rate=Decimal("800"),
            quantity=5,
        )

        # The old scenario should have been deleted
        db.delete.assert_called_once_with(old_scenario)
        assert scenario.name == "New Scenario"
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_scenario_with_product_id(self):
        """Save a scenario linked to a product."""
        db = _mock_db()
        product_id = uuid.uuid4()

        count_result = MagicMock()
        count_result.scalar.return_value = 0
        db.execute = AsyncMock(return_value=count_result)

        scenario = await save_scenario(
            db,
            name="Product Scenario",
            user_id=uuid.uuid4(),
            business_id=uuid.uuid4(),
            selling_price=Decimal("60000"),
            fx_rate=Decimal("750"),
            quantity=20,
            product_id=product_id,
        )

        assert scenario.product_id == product_id


# ---------------------------------------------------------------------------
# Selling price suggestion tests
# ---------------------------------------------------------------------------


class TestSellingPriceSuggestion:
    @pytest.mark.asyncio
    async def test_suggestion_ngn_currency_no_fx(self):
        """NGN unit cost needs no FX conversion; min price = cost / (1 - margin)."""
        db = _mock_db()

        result = await get_selling_price_suggestion(
            db,
            product_id=None,
            unit_cost_override=Decimal("10000"),
            currency="NGN",
            fx_rate_override=None,
            min_margin_pct=Decimal("35"),
        )

        assert result["currency"] == "NGN"
        assert result["fx_rate"] == Decimal("1")
        assert result["unit_cost_ngn"] == Decimal("10000")
        # min_selling_price = 10000 / (1 - 0.35) = 10000 / 0.65 ≈ 15384.615384
        assert result["min_selling_price"] > Decimal("15384")
        assert result["min_selling_price"] < Decimal("15385")
        assert result["min_margin_pct"] == Decimal("35")

    @pytest.mark.asyncio
    async def test_suggestion_usd_currency_with_fx_override(self):
        """USD unit cost is multiplied by FX rate override to get NGN cost."""
        db = _mock_db()

        result = await get_selling_price_suggestion(
            db,
            product_id=None,
            unit_cost_override=Decimal("10"),
            currency="USD",
            fx_rate_override=Decimal("1600"),
            min_margin_pct=Decimal("35"),
        )

        assert result["currency"] == "USD"
        assert result["fx_rate"] == Decimal("1600")
        assert result["unit_cost_ngn"] == Decimal("16000")
        # min = 16000 / 0.65 ≈ 24615.38...
        assert result["min_selling_price"] > Decimal("24615")
        assert result["min_selling_price"] < Decimal("24616")

    @pytest.mark.asyncio
    async def test_suggestion_custom_margin(self):
        """Custom min_margin_pct updates the suggested price accordingly."""
        db = _mock_db()

        result_50 = await get_selling_price_suggestion(
            db,
            product_id=None,
            unit_cost_override=Decimal("20000"),
            currency="NGN",
            fx_rate_override=None,
            min_margin_pct=Decimal("50"),
        )
        # min = 20000 / 0.50 = 40000
        assert result_50["min_selling_price"] == Decimal("40000.000000")

    @pytest.mark.asyncio
    async def test_suggestion_with_product_id_ngn(self):
        """product_id lookup uses product's unit_cost and currency."""
        db = _mock_db()
        product_id = uuid.uuid4()

        product = MagicMock()
        product.id = product_id
        product.unit_cost = Decimal("5000.000000")
        product.currency = "NGN"
        product.selling_price = Decimal("7000.000000")

        with patch(
            "src.pricing.service._get_product",
            new_callable=AsyncMock,
            return_value=product,
        ):
            result = await get_selling_price_suggestion(
                db,
                product_id=product_id,
                unit_cost_override=None,
                currency="NGN",
                fx_rate_override=None,
                min_margin_pct=Decimal("35"),
            )

        assert result["unit_cost_ngn"] == Decimal("5000.000000")
        assert result["min_selling_price"] > Decimal("7692")

    @pytest.mark.asyncio
    async def test_suggestion_margin_100_raises(self):
        """min_margin_pct of 100 produces a division-by-zero and should raise."""
        db = _mock_db()

        with pytest.raises(ValueError, match="min_margin_pct must be less than 100"):
            await get_selling_price_suggestion(
                db,
                product_id=None,
                unit_cost_override=Decimal("1000"),
                currency="NGN",
                fx_rate_override=None,
                min_margin_pct=Decimal("100"),
            )

    @pytest.mark.asyncio
    async def test_suggestion_usd_fetches_live_rate_when_no_override(self):
        """When no fx_rate_override and currency==USD, fetch live USDNGN rate."""
        db = _mock_db()

        from datetime import datetime, timezone

        mock_rate = MagicMock()
        mock_rate.rate = Decimal("1650")
        mock_rate.timestamp = datetime.now(timezone.utc)
        mock_rate.source.value = "api_provider"

        with patch(
            "src.fx.service.get_current_rate",
            new_callable=AsyncMock,
            return_value=mock_rate,
        ):
            result = await get_selling_price_suggestion(
                db,
                product_id=None,
                unit_cost_override=Decimal("20"),
                currency="USD",
                fx_rate_override=None,
                min_margin_pct=Decimal("35"),
            )

        assert result["fx_rate"] == Decimal("1650")
        assert result["unit_cost_ngn"] == Decimal("33000")
        assert result["fx_rate_stale"] is False


class TestScenarioList:
    @pytest.mark.asyncio
    async def test_list_scenarios(self):
        """List scenarios returns results."""
        db = _mock_db()

        s1 = MagicMock(spec=PricingScenario)
        s2 = MagicMock(spec=PricingScenario)

        result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [s1, s2]
        result.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result)

        scenarios = await list_scenarios(db, uuid.uuid4(), business_id=uuid.uuid4())
        assert len(scenarios) == 2

    @pytest.mark.asyncio
    async def test_list_scenarios_empty(self):
        """List scenarios returns empty when no scenarios exist."""
        db = _mock_db()

        result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result)

        scenarios = await list_scenarios(db, uuid.uuid4(), business_id=uuid.uuid4())
        assert scenarios == []
