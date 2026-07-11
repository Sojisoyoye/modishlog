"""Tests for backend/src/data_import/recompute.py.

recompute_after_import() fills the gaps etl/loader.py's own docstrings admit
it leaves: imported sales never call adjust_stock()/fifo_deduct(), imported
products get no price history, and AI reorder/price signals are never
regenerated after a bulk import. Every private step is tested for its own
logic; the orchestrator is tested for error isolation (one step's failure
must not stop the others, or propagate to the caller).
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.inventory.exceptions import (
    InvalidStockAdjustmentError,
    ProductStockNotFoundError,
)
from src.inventory.models import MovementType
from src.pricing.exceptions import PricingSuggestionError

# orders/models.py's PurchaseOrder<->Supplier relationship is only resolved
# once both classes are registered — recompute.py itself never imports
# orders.models or suppliers.models, so nothing else in this file's import
# chain triggers it. Constructing InventoryLevel/PriceHistory/LowStockAlert
# below would otherwise fail mapper configuration when this file runs in
# isolation (mirrors etl/loader.py's own direct Supplier import).
from src.orders import models as _orders_models  # noqa: F401
from src.suppliers.models import Supplier  # noqa: F401

BUSINESS_ID = uuid.uuid4()
JOB_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    return db


def _rows_result(rows):
    r = MagicMock()
    r.all.return_value = rows
    return r


def _scalars_result(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _scalar_one_or_none_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _scalar_result(value):
    r = MagicMock()
    r.scalar.return_value = value
    return r


# ---------------------------------------------------------------------------
# _deduct_imported_sales_stock
# ---------------------------------------------------------------------------


class TestDeductImportedSalesStock:
    @pytest.mark.asyncio
    async def test_aggregates_sales_and_deducts_once_per_product_variant_group(self):
        from src.data_import.recompute import _deduct_imported_sales_stock

        product_id = uuid.uuid4()
        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _rows_result([]),  # no groups already applied
                _rows_result([(product_id, None, 15)]),  # aggregate group query
                MagicMock(),  # migration_id tag sweep on the new StockMovement
            ]
        )

        with patch(
            "src.data_import.recompute.adjust_stock", new=AsyncMock()
        ) as mock_adjust:
            errors = await _deduct_imported_sales_stock(
                db, BUSINESS_ID, JOB_ID, USER_ID
            )

        assert errors == []
        mock_adjust.assert_awaited_once()
        _, kwargs = mock_adjust.call_args
        assert kwargs["product_id"] == product_id
        assert kwargs["quantity_change"] == -15
        assert kwargs["movement_type"] == MovementType.SALE_DEPLETION.value
        assert kwargs["variant_id"] is None
        assert kwargs["business_id"] == BUSINESS_ID
        assert kwargs["reference_id"] == JOB_ID
        assert kwargs["reference_type"] == "data_import_recompute"
        # 1 already-applied check + 1 aggregate query + 1 tag sweep — the
        # sweep must run so rollback's reversal-delta calculation (which
        # sums StockMovement rows tagged with this migration_id) can find
        # these movements too.
        assert db.execute.await_count == 3

    @pytest.mark.asyncio
    async def test_no_imported_sales_is_a_noop(self):
        from src.data_import.recompute import _deduct_imported_sales_stock

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[_scalar_one_or_none_result(None), _rows_result([])]
        )

        with patch(
            "src.data_import.recompute.adjust_stock", new=AsyncMock()
        ) as mock_adjust:
            errors = await _deduct_imported_sales_stock(
                db, BUSINESS_ID, JOB_ID, USER_ID
            )

        assert errors == []
        mock_adjust.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_variant_level_inventory_row_is_created_before_deducting(
        self,
    ):
        """load() only ever creates a product-level (variant_id=None)
        InventoryLevel row — never a variant-level one. Unlike PO delivery
        (which reuses transition_status()/create_batch() unmodified and has
        no variant-aware path), this step calls adjust_stock() directly and
        CAN pass variant_id, so it must create whatever variant-level rows
        are missing first instead of letting adjust_stock() raise
        ProductStockNotFoundError."""
        from src.data_import.recompute import _deduct_imported_sales_stock

        product_id, variant_id = uuid.uuid4(), uuid.uuid4()
        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _rows_result([]),  # no groups already applied
                _rows_result([(product_id, variant_id, 5)]),
                _rows_result([]),  # no existing variant-level InventoryLevel rows
                _scalars_result([product_id]),  # product IS new (migration_id==job_id)
                MagicMock(),  # migration_id tag sweep on the new StockMovement
            ]
        )

        with patch(
            "src.data_import.recompute.adjust_stock", new=AsyncMock()
        ) as mock_adjust:
            errors = await _deduct_imported_sales_stock(
                db, BUSINESS_ID, JOB_ID, USER_ID
            )

        assert errors == []
        assert db.add.call_count == 1
        created = db.add.call_args[0][0]
        assert created.product_id == product_id
        assert created.variant_id == variant_id
        assert created.quantity_on_hand == 0
        # The product is new (migration_id == job_id) — the new
        # variant-level row must be tagged too, or rollback's generic
        # migration_id-scoped delete would orphan it and later fail
        # deleting the product with an FK violation.
        assert created.migration_id == JOB_ID
        mock_adjust.assert_awaited_once()
        assert mock_adjust.call_args.kwargs["variant_id"] == variant_id

    @pytest.mark.asyncio
    async def test_missing_variant_row_for_a_deduped_product_is_left_untagged(self):
        """Mirrors etl/loader.py's _zeroed_inventory_level() precedent —
        tagging a deduped (pre-existing) product's new row with this
        migration_id would make rollback incorrectly delete a row for a
        product it didn't create."""
        from src.data_import.recompute import _deduct_imported_sales_stock

        product_id, variant_id = uuid.uuid4(), uuid.uuid4()
        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _rows_result([]),
                _rows_result([(product_id, variant_id, 5)]),
                _rows_result([]),
                _scalars_result([]),  # product is NOT new — deduped
                MagicMock(),
            ]
        )

        with patch("src.data_import.recompute.adjust_stock", new=AsyncMock()):
            await _deduct_imported_sales_stock(db, BUSINESS_ID, JOB_ID, USER_ID)

        created = db.add.call_args[0][0]
        assert created.migration_id is None

    @pytest.mark.asyncio
    async def test_one_groups_negative_stock_error_does_not_stop_the_others(self):
        """Imported sale history can easily exceed imported PO history (e.g.
        a business imports a year of sales but only 6 months of POs) —
        adjust_stock() rejects going negative. That must be recorded per
        group, not abort every other product's deduction."""
        from src.data_import.recompute import _deduct_imported_sales_stock

        product_a, product_b = uuid.uuid4(), uuid.uuid4()
        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _rows_result([]),  # no groups already applied
                _rows_result([(product_a, None, 100), (product_b, None, 5)]),
                MagicMock(),  # migration_id tag sweep (product_b succeeded)
            ]
        )

        with patch(
            "src.data_import.recompute.adjust_stock",
            new=AsyncMock(
                side_effect=[
                    InvalidStockAdjustmentError(product_a, -100, 10),
                    MagicMock(),
                ]
            ),
        ) as mock_adjust:
            errors = await _deduct_imported_sales_stock(
                db, BUSINESS_ID, JOB_ID, USER_ID
            )

        assert mock_adjust.await_count == 2
        assert len(errors) == 1
        assert str(product_a) in errors[0]["error"] or "product_id" in errors[0]

    @pytest.mark.asyncio
    async def test_no_tag_sweep_when_every_deduction_fails(self):
        from src.data_import.recompute import _deduct_imported_sales_stock

        product_id = uuid.uuid4()
        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _rows_result([]),  # no groups already applied
                _rows_result([(product_id, None, 5)]),
            ]
        )

        with patch(
            "src.data_import.recompute.adjust_stock",
            new=AsyncMock(side_effect=ProductStockNotFoundError(product_id)),
        ):
            errors = await _deduct_imported_sales_stock(
                db, BUSINESS_ID, JOB_ID, USER_ID
            )

        assert len(errors) == 1
        # Already-applied check + aggregate query — no tag sweep since
        # nothing succeeded to tag.
        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_already_applied_group_is_skipped_but_others_still_run(self):
        """A second call (via POST /jobs/{id}/recompute) must not deduct an
        already-tagged (product, variant) group's stock again — but a
        step-level 'any tag exists -> skip everything' check would
        permanently strand any OTHER group that failed (or was never
        reached) on the first attempt. Only the specific already-applied
        group is skipped; the rest of the groups still run normally."""
        from src.data_import.recompute import _deduct_imported_sales_stock

        done_product, pending_product = uuid.uuid4(), uuid.uuid4()
        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _rows_result([(done_product, None)]),  # already-applied pairs
                _rows_result([(done_product, None, 5), (pending_product, None, 3)]),
                MagicMock(),  # tag sweep for the newly-succeeded group
            ]
        )

        with patch(
            "src.data_import.recompute.adjust_stock", new=AsyncMock()
        ) as mock_adjust:
            errors = await _deduct_imported_sales_stock(
                db, BUSINESS_ID, JOB_ID, USER_ID
            )

        assert errors == []
        mock_adjust.assert_awaited_once()
        assert mock_adjust.call_args.kwargs["product_id"] == pending_product


# ---------------------------------------------------------------------------
# _compute_fifo_cogs_for_imported_sales
# ---------------------------------------------------------------------------


class TestComputeFifoCogsForImportedSales:
    @pytest.mark.asyncio
    async def test_sets_fifo_cogs_and_gross_profit_from_fifo_deduct(self):
        from src.data_import.recompute import _compute_fifo_cogs_for_imported_sales

        sale = MagicMock()
        sale.id = uuid.uuid4()
        sale.product_id = uuid.uuid4()
        sale.quantity = 3
        sale.total_amount = Decimal("300")

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[_scalars_result([sale]), _scalar_result(3)])

        with patch(
            "src.data_import.recompute.fifo_deduct",
            new=AsyncMock(return_value=Decimal("180")),
        ):
            errors = await _compute_fifo_cogs_for_imported_sales(db, JOB_ID)

        assert errors == []
        assert sale.fifo_cogs == Decimal("180")
        assert sale.fifo_gross_profit == Decimal("120")

    @pytest.mark.asyncio
    async def test_one_sales_fifo_failure_does_not_stop_the_others(self):
        from src.data_import.recompute import _compute_fifo_cogs_for_imported_sales

        sale_a, sale_b = MagicMock(), MagicMock()
        sale_a.id, sale_b.id = uuid.uuid4(), uuid.uuid4()
        sale_a.product_id, sale_b.product_id = uuid.uuid4(), uuid.uuid4()
        sale_a.quantity, sale_b.quantity = 1, 2
        sale_a.total_amount, sale_b.total_amount = Decimal("10"), Decimal("20")

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_result([sale_a, sale_b]),
                _scalar_result(1),
                _scalar_result(2),
            ]
        )

        with patch(
            "src.data_import.recompute.fifo_deduct",
            new=AsyncMock(side_effect=[RuntimeError("db blew up"), Decimal("8")]),
        ):
            errors = await _compute_fifo_cogs_for_imported_sales(db, JOB_ID)

        assert len(errors) == 1
        assert sale_b.fifo_cogs == Decimal("8")

    @pytest.mark.asyncio
    async def test_query_excludes_sales_that_already_have_fifo_cogs(self):
        """Re-running (via POST /jobs/{id}/recompute) must not re-consume
        InventoryBatch.quantity_remaining for a sale that was already
        matched — fifo_deduct() has no notion of 'already done', so the
        query itself is the only thing that can make this idempotent."""
        from src.data_import.recompute import _compute_fifo_cogs_for_imported_sales

        db = _mock_db()
        db.execute = AsyncMock(return_value=_scalars_result([]))

        await _compute_fifo_cogs_for_imported_sales(db, JOB_ID)

        compiled_where = str(
            db.execute.call_args[0][0].whereclause.compile(
                compile_kwargs={"literal_binds": True}
            )
        )
        assert "fifo_cogs IS NULL" in compiled_where

    @pytest.mark.asyncio
    async def test_insufficient_batches_reported_as_an_error_not_silently_understated(
        self,
    ):
        """fifo_deduct() only logs a warning (never raises) when batches
        run short, returning whatever partial COGS it could match — with
        no signal distinguishing that from a fully-matched result. The
        caller must surface the shortfall itself so understated COGS/
        overstated gross-profit isn't silently mistaken for a clean
        result."""
        from src.data_import.recompute import _compute_fifo_cogs_for_imported_sales

        sale = MagicMock()
        sale.id = uuid.uuid4()
        sale.product_id = uuid.uuid4()
        sale.quantity = 10
        sale.total_amount = Decimal("1000")

        db = _mock_db()
        # Only 4 units of matching batch remain for a 10-unit sale.
        db.execute = AsyncMock(side_effect=[_scalars_result([sale]), _scalar_result(4)])

        with patch(
            "src.data_import.recompute.fifo_deduct",
            new=AsyncMock(return_value=Decimal("40")),
        ):
            errors = await _compute_fifo_cogs_for_imported_sales(db, JOB_ID)

        assert len(errors) == 1
        assert errors[0]["sale_id"] == str(sale.id)
        assert "4" in errors[0]["error"] and "10" in errors[0]["error"]
        # Still records the partial result — some COGS is better than none.
        assert sale.fifo_cogs == Decimal("40")


# ---------------------------------------------------------------------------
# _create_opening_price_history
# ---------------------------------------------------------------------------


class TestCreateOpeningPriceHistory:
    @pytest.mark.asyncio
    async def test_creates_one_row_per_imported_product_from_current_prices(self):
        from src.data_import.recompute import _create_opening_price_history

        product = MagicMock()
        product.id = uuid.uuid4()
        product.unit_cost = Decimal("500")
        product.selling_price = Decimal("900")
        product.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[_scalars_result([]), _scalars_result([product])]
        )

        await _create_opening_price_history(db, JOB_ID, USER_ID)

        db.add.assert_called_once()
        row = db.add.call_args[0][0]
        assert row.product_id == product.id
        assert row.old_unit_cost == Decimal("500")
        assert row.new_unit_cost == Decimal("500")
        assert row.old_selling_price == Decimal("900")
        assert row.new_selling_price == Decimal("900")
        assert row.effective_date == date(2025, 1, 1)
        assert row.changed_by == USER_ID
        assert row.migration_id == JOB_ID

    @pytest.mark.asyncio
    async def test_no_imported_products_is_a_noop(self):
        from src.data_import.recompute import _create_opening_price_history

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[_scalars_result([]), _scalars_result([])])

        await _create_opening_price_history(db, JOB_ID, USER_ID)

        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_a_product_that_already_has_an_opening_row(self):
        """Re-running (via POST /jobs/{id}/recompute) must not create a
        second 'Opening balance from import' row for the same product —
        that would double-count in any P&L/price-history report."""
        from src.data_import.recompute import _create_opening_price_history

        already_seeded_product = MagicMock()
        already_seeded_product.id = uuid.uuid4()
        pending_product = MagicMock()
        pending_product.id = uuid.uuid4()
        pending_product.unit_cost = Decimal("100")
        pending_product.selling_price = Decimal("200")
        pending_product.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_result([already_seeded_product.id]),
                _scalars_result([already_seeded_product, pending_product]),
            ]
        )

        await _create_opening_price_history(db, JOB_ID, USER_ID)

        db.add.assert_called_once()
        assert db.add.call_args[0][0].product_id == pending_product.id


# ---------------------------------------------------------------------------
# _recompute_low_stock_alerts
# ---------------------------------------------------------------------------


class TestRecomputeLowStockAlerts:
    @pytest.mark.asyncio
    async def test_creates_alert_when_quantity_at_or_below_threshold(self):
        from src.data_import.recompute import _recompute_low_stock_alerts

        inv = MagicMock()
        inv.product_id = uuid.uuid4()
        inv.quantity_on_hand = 2
        inv.low_stock_threshold = 10

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _rows_result([(inv, JOB_ID)]),
                _scalar_one_or_none_result(None),  # no existing ACTIVE alert
            ]
        )

        await _recompute_low_stock_alerts(db, JOB_ID)

        db.add.assert_called_once()
        alert = db.add.call_args[0][0]
        assert alert.product_id == inv.product_id
        assert alert.current_quantity == 2
        assert alert.threshold == 10

    @pytest.mark.asyncio
    async def test_skips_when_quantity_above_threshold(self):
        from src.data_import.recompute import _recompute_low_stock_alerts

        inv = MagicMock()
        inv.product_id = uuid.uuid4()
        inv.quantity_on_hand = 50
        inv.low_stock_threshold = 10

        db = _mock_db()
        db.execute = AsyncMock(return_value=_rows_result([(inv, JOB_ID)]))

        await _recompute_low_stock_alerts(db, JOB_ID)

        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_duplicate_an_existing_active_alert(self):
        from src.data_import.recompute import _recompute_low_stock_alerts

        inv = MagicMock()
        inv.product_id = uuid.uuid4()
        inv.quantity_on_hand = 1
        inv.low_stock_threshold = 10

        db = _mock_db()
        existing_alert = MagicMock()
        db.execute = AsyncMock(
            side_effect=[
                _rows_result([(inv, JOB_ID)]),
                _scalar_one_or_none_result(existing_alert),
            ]
        )

        await _recompute_low_stock_alerts(db, JOB_ID)

        db.add.assert_not_called()


# ---------------------------------------------------------------------------
# _recompute_ai_signals
# ---------------------------------------------------------------------------


class TestRecomputeAiSignals:
    @pytest.mark.asyncio
    async def test_clears_pending_suggestions_then_regenerates_and_computes_prices(
        self,
    ):
        from src.data_import.recompute import _recompute_ai_signals

        product_id = uuid.uuid4()
        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(),  # delete(...) pending suggestions
                _scalars_result([product_id]),  # imported product ids
            ]
        )

        with (
            patch(
                "src.data_import.recompute.generate_reorder_suggestions",
                new=AsyncMock(return_value=[]),
            ) as mock_reorder,
            patch(
                "src.data_import.recompute.compute_suggestion", new=AsyncMock()
            ) as mock_price,
        ):
            errors = await _recompute_ai_signals(db, BUSINESS_ID, JOB_ID)

        assert errors == []
        mock_reorder.assert_awaited_once_with(db, BUSINESS_ID)
        mock_price.assert_awaited_once_with(db, product_id)

    @pytest.mark.asyncio
    async def test_one_products_pricing_failure_does_not_stop_the_others(self):
        from src.data_import.recompute import _recompute_ai_signals

        product_a, product_b = uuid.uuid4(), uuid.uuid4()
        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[MagicMock(), _scalars_result([product_a, product_b])]
        )

        with (
            patch(
                "src.data_import.recompute.generate_reorder_suggestions",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "src.data_import.recompute.compute_suggestion",
                new=AsyncMock(
                    side_effect=[
                        PricingSuggestionError(product_a, "no active lots"),
                        MagicMock(),
                    ]
                ),
            ) as mock_price,
        ):
            errors = await _recompute_ai_signals(db, BUSINESS_ID, JOB_ID)

        assert mock_price.await_count == 2
        assert len(errors) == 1
        assert errors[0]["product_id"] == str(product_a)

    @pytest.mark.asyncio
    async def test_reorder_suggestion_failure_does_not_block_pricing_suggestions(self):
        from src.data_import.recompute import _recompute_ai_signals

        product_id = uuid.uuid4()
        db = _mock_db()
        db.execute = AsyncMock(side_effect=[MagicMock(), _scalars_result([product_id])])

        with (
            patch(
                "src.data_import.recompute.generate_reorder_suggestions",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
            patch(
                "src.data_import.recompute.compute_suggestion", new=AsyncMock()
            ) as mock_price,
        ):
            errors = await _recompute_ai_signals(db, BUSINESS_ID, JOB_ID)

        assert any(e["step"] == "reorder_suggestions" for e in errors)
        mock_price.assert_awaited_once()


# ---------------------------------------------------------------------------
# recompute_after_import — orchestration / error isolation
# ---------------------------------------------------------------------------


class TestRecomputeAfterImport:
    @pytest.mark.asyncio
    async def test_runs_every_step_and_collects_no_errors_on_the_happy_path(self):
        from src.data_import.recompute import recompute_after_import

        with (
            patch(
                "src.data_import.recompute._deduct_imported_sales_stock",
                new=AsyncMock(return_value=[]),
            ) as m1,
            patch(
                "src.data_import.recompute._compute_fifo_cogs_for_imported_sales",
                new=AsyncMock(return_value=[]),
            ) as m2,
            patch(
                "src.data_import.recompute._create_opening_price_history",
                new=AsyncMock(),
            ) as m3,
            patch(
                "src.data_import.recompute._recompute_low_stock_alerts",
                new=AsyncMock(),
            ) as m4,
            patch(
                "src.data_import.recompute._recompute_ai_signals",
                new=AsyncMock(return_value=[]),
            ) as m5,
        ):
            result = await recompute_after_import(
                _mock_db(), BUSINESS_ID, JOB_ID, USER_ID
            )

        assert result["errors"] == []
        for m in (m1, m2, m3, m4, m5):
            m.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_one_steps_unexpected_exception_does_not_stop_later_steps(self):
        """Every step is independently isolated — an unhandled exception in
        one step (not just a per-item error the step already catches
        itself) must not prevent the remaining steps from running, since
        the import itself has already committed and each step operates on
        an independent slice of derived state."""
        from src.data_import.recompute import recompute_after_import

        with (
            patch(
                "src.data_import.recompute._deduct_imported_sales_stock",
                new=AsyncMock(side_effect=RuntimeError("unexpected")),
            ),
            patch(
                "src.data_import.recompute._compute_fifo_cogs_for_imported_sales",
                new=AsyncMock(return_value=[]),
            ) as m2,
            patch(
                "src.data_import.recompute._create_opening_price_history",
                new=AsyncMock(),
            ) as m3,
            patch(
                "src.data_import.recompute._recompute_low_stock_alerts",
                new=AsyncMock(),
            ) as m4,
            patch(
                "src.data_import.recompute._recompute_ai_signals",
                new=AsyncMock(return_value=[]),
            ) as m5,
        ):
            result = await recompute_after_import(
                _mock_db(), BUSINESS_ID, JOB_ID, USER_ID
            )

        assert any(e["step"] == "deduct_sales_stock" for e in result["errors"])
        for m in (m2, m3, m4, m5):
            m.assert_awaited_once()
