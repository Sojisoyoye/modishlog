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
from tests.conftest import NestedTransaction as _NestedTransaction
from tests.conftest import mock_db as _mock_db

BUSINESS_ID = uuid.uuid4()
JOB_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


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


def _make_product_for_recompute(product_id=None, variant_ids=None):
    """A Product stand-in for _recompute_ai_signals()'s per-product loop —
    has_variants=True with N variants when variant_ids is given, else a
    plain non-variant product (mirrors the real Product.has_variants /
    Product.variants relationship, task 171's fix)."""
    p = MagicMock()
    p.id = product_id or uuid.uuid4()
    if variant_ids:
        p.has_variants = True
        p.variants = [MagicMock(id=vid) for vid in variant_ids]
    else:
        p.has_variants = False
        p.variants = []
    return p


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
                _rows_result([(product_id, None)]),  # InventoryLevel already exists
            ]
        )

        with patch(
            "src.data_import.recompute.adjust_stock", new=AsyncMock()
        ) as mock_adjust:
            errors, failed_pairs = await _deduct_imported_sales_stock(
                db, BUSINESS_ID, JOB_ID, USER_ID
            )

        assert errors == []
        assert failed_pairs == set()
        mock_adjust.assert_awaited_once()
        _, kwargs = mock_adjust.call_args
        assert kwargs["product_id"] == product_id
        assert kwargs["quantity_change"] == -15
        assert kwargs["movement_type"] == MovementType.SALE_DEPLETION.value
        assert kwargs["variant_id"] is None
        assert kwargs["business_id"] == BUSINESS_ID
        assert kwargs["reference_id"] == JOB_ID
        assert kwargs["reference_type"] == "data_import_recompute"
        # adjust_stock() is tagged with migration_id directly at insert
        # time now — no separate tag-sweep UPDATE afterward.
        assert kwargs["migration_id"] == JOB_ID
        # 1 already-applied check + 1 aggregate query + 1 InventoryLevel
        # existence check.
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
            errors, failed_pairs = await _deduct_imported_sales_stock(
                db, BUSINESS_ID, JOB_ID, USER_ID
            )

        assert errors == []
        assert failed_pairs == set()
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
            ]
        )

        with patch(
            "src.data_import.recompute.adjust_stock", new=AsyncMock()
        ) as mock_adjust:
            errors, failed_pairs = await _deduct_imported_sales_stock(
                db, BUSINESS_ID, JOB_ID, USER_ID
            )

        assert errors == []
        assert failed_pairs == set()
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
            ]
        )

        with patch("src.data_import.recompute.adjust_stock", new=AsyncMock()):
            await _deduct_imported_sales_stock(db, BUSINESS_ID, JOB_ID, USER_ID)

        created = db.add.call_args[0][0]
        assert created.migration_id is None

    @pytest.mark.asyncio
    async def test_inventory_level_backfill_failure_is_isolated_per_pair(self):
        """A collision on the new partial unique indexes (e.g. a concurrent
        recompute retrigger backfilling the same missing pair) must fail
        only that one pair — recorded as an error and skipped, adjust_stock
        never called for it — not raise out of an unguarded flush() and
        poison the whole outer transaction this step (and every later
        recompute step) runs inside."""
        from sqlalchemy.exc import IntegrityError

        from src.data_import.recompute import _deduct_imported_sales_stock

        product_id, variant_id = uuid.uuid4(), uuid.uuid4()
        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _rows_result([]),
                _rows_result([(product_id, variant_id, 5)]),
                _rows_result([]),  # no existing InventoryLevel row
                _scalars_result([product_id]),  # product IS new
            ]
        )
        db.flush = AsyncMock(
            side_effect=IntegrityError(
                "INSERT", {}, Exception("duplicate key value violates unique constraint")
            )
        )

        with patch(
            "src.data_import.recompute.adjust_stock", new=AsyncMock()
        ) as mock_adjust:
            errors, failed_pairs = await _deduct_imported_sales_stock(
                db, BUSINESS_ID, JOB_ID, USER_ID
            )

        assert failed_pairs == {(product_id, variant_id)}
        assert len(errors) == 1
        mock_adjust.assert_not_awaited()
        db.begin_nested.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_product_level_inventory_row_is_also_backfilled(self):
        """load()/load_purchase_orders() aren't guaranteed to have created a
        product-level (variant_id=None) InventoryLevel row for a deduped
        product either (see load_purchase_orders()'s identical defensive
        backfill in etl/loader.py, for the same reason) — a sale against
        such a product with no variant reference must not fail with
        ProductStockNotFoundError just because only the variant-level
        backfill was implemented."""
        from src.data_import.recompute import _deduct_imported_sales_stock

        product_id = uuid.uuid4()
        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _rows_result([]),
                _rows_result([(product_id, None, 5)]),
                _rows_result([]),  # no InventoryLevel row exists at all
                _scalars_result([]),  # product is NOT new — deduped
            ]
        )

        with patch(
            "src.data_import.recompute.adjust_stock", new=AsyncMock()
        ) as mock_adjust:
            errors, failed_pairs = await _deduct_imported_sales_stock(
                db, BUSINESS_ID, JOB_ID, USER_ID
            )

        assert errors == []
        assert failed_pairs == set()
        assert db.add.call_count == 1
        created = db.add.call_args[0][0]
        assert created.product_id == product_id
        assert created.variant_id is None
        assert created.migration_id is None
        mock_adjust.assert_awaited_once()

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
                _rows_result(
                    [(product_a, None), (product_b, None)]
                ),  # InventoryLevel rows already exist
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
            errors, failed_pairs = await _deduct_imported_sales_stock(
                db, BUSINESS_ID, JOB_ID, USER_ID
            )

        assert mock_adjust.await_count == 2
        assert len(errors) == 1
        assert str(product_a) in errors[0]["error"] or "product_id" in errors[0]
        assert failed_pairs == {(product_a, None)}

    @pytest.mark.asyncio
    async def test_every_deduction_failing_reports_all_as_failed_pairs(self):
        from src.data_import.recompute import _deduct_imported_sales_stock

        product_id = uuid.uuid4()
        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _rows_result([]),  # no groups already applied
                _rows_result([(product_id, None, 5)]),
                _rows_result([(product_id, None)]),  # InventoryLevel already exists
            ]
        )

        with patch(
            "src.data_import.recompute.adjust_stock",
            new=AsyncMock(side_effect=ProductStockNotFoundError(product_id)),
        ):
            errors, failed_pairs = await _deduct_imported_sales_stock(
                db, BUSINESS_ID, JOB_ID, USER_ID
            )

        assert len(errors) == 1
        assert failed_pairs == {(product_id, None)}
        # Already-applied check + aggregate query + InventoryLevel
        # existence check — migration_id is passed to adjust_stock()
        # directly now, no follow-up tag-sweep query.
        assert db.execute.await_count == 3

    @pytest.mark.asyncio
    async def test_adjust_stock_is_wrapped_in_a_per_item_savepoint(self):
        """A real DB-level failure inside adjust_stock() (a constraint
        violation, not just its own Python-level exceptions) would
        otherwise poison the single SAVEPOINT the whole recompute runs
        inside, breaking every later group and every later recompute step.
        Each group's adjust_stock() call must open — and roll back to —
        its own nested SAVEPOINT."""
        from src.data_import.recompute import _deduct_imported_sales_stock

        product_id = uuid.uuid4()
        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _rows_result([]),
                _rows_result([(product_id, None, 5)]),
                _rows_result([(product_id, None)]),  # InventoryLevel already exists
            ]
        )

        with patch("src.data_import.recompute.adjust_stock", new=AsyncMock()):
            await _deduct_imported_sales_stock(db, BUSINESS_ID, JOB_ID, USER_ID)

        db.begin_nested.assert_called_once()

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
                _rows_result(
                    [(done_product, None), (pending_product, None)]
                ),  # InventoryLevel rows already exist
            ]
        )

        with patch(
            "src.data_import.recompute.adjust_stock", new=AsyncMock()
        ) as mock_adjust:
            errors, failed_pairs = await _deduct_imported_sales_stock(
                db, BUSINESS_ID, JOB_ID, USER_ID
            )

        assert errors == []
        assert failed_pairs == set()
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
    async def test_passes_sale_variant_id_to_fifo_deduct(self):
        """An imported sale for a specific variant must scope its FIFO
        cost matching to that variant — otherwise recompute would silently
        pool landed cost across sibling variants of the same product (the
        same class of bug already fixed for the live create_sale() path)."""
        from src.data_import.recompute import _compute_fifo_cogs_for_imported_sales

        sale = MagicMock()
        sale.id = uuid.uuid4()
        sale.product_id = uuid.uuid4()
        sale.variant_id = uuid.uuid4()
        sale.quantity = 3
        sale.total_amount = Decimal("300")

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[_scalars_result([sale]), _scalar_result(3)])

        with patch(
            "src.data_import.recompute.fifo_deduct",
            new=AsyncMock(return_value=Decimal("180")),
        ) as mock_fifo_deduct:
            await _compute_fifo_cogs_for_imported_sales(db, JOB_ID)

        mock_fifo_deduct.assert_awaited_once_with(
            db, sale.product_id, sale.quantity, variant_id=sale.variant_id, sale_id=sale.id
        )

    @pytest.mark.asyncio
    async def test_availability_precheck_scopes_to_the_same_variant_filter(self):
        """The insufficient-batches pre-check must count the same set of
        batches fifo_deduct() itself will draw from (variant-tagged +
        untagged) — otherwise it could wrongly flag a sale as understated
        (or miss a real shortfall) by counting a sibling variant's batches
        that fifo_deduct() would never actually touch."""
        from src.data_import.recompute import _compute_fifo_cogs_for_imported_sales

        sale = MagicMock()
        sale.id = uuid.uuid4()
        sale.product_id = uuid.uuid4()
        sale.variant_id = uuid.uuid4()
        sale.quantity = 3
        sale.total_amount = Decimal("300")

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[_scalars_result([sale]), _scalar_result(3)])

        with patch(
            "src.data_import.recompute.fifo_deduct",
            new=AsyncMock(return_value=Decimal("180")),
        ):
            await _compute_fifo_cogs_for_imported_sales(db, JOB_ID)

        precheck_stmt = db.execute.await_args_list[1].args[0]
        compiled = str(
            precheck_stmt.compile(compile_kwargs={"literal_binds": True})
        ).lower()
        assert "inventory_batches.variant_id is null" in compiled
        assert sale.variant_id.hex in compiled.replace("-", "")

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
        caller must surface the shortfall itself so understated COGS isn't
        silently mistaken for a clean result, and fifo_gross_profit (which
        a P&L report may read directly, without ever seeing
        recompute_errors) must not be left holding a precise-looking but
        silently overstated value derived from that understated COGS."""
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
        # But gross_profit built on that understated COGS is left unset
        # rather than silently overstated.
        assert sale.fifo_gross_profit is None

    @pytest.mark.asyncio
    async def test_fifo_deduct_is_wrapped_in_a_per_item_savepoint(self):
        """A real DB-level failure inside fifo_deduct() (a constraint
        violation from its own flush, not just an unhandled Python
        exception) would otherwise poison the single SAVEPOINT the whole
        recompute runs inside, breaking every later sale and every later
        recompute step. Each sale's fifo_deduct() call must open — and
        roll back to — its own nested SAVEPOINT."""
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
            new=AsyncMock(return_value=Decimal("100")),
        ):
            await _compute_fifo_cogs_for_imported_sales(db, JOB_ID)

        db.begin_nested.assert_called_once()


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

        product_id = uuid.uuid4()
        inv = MagicMock()
        inv.product_id = product_id
        inv.quantity_on_hand = 2
        inv.low_stock_threshold = 10

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_result([product_id]),  # relevant products (new/sold)
                _scalars_result([inv]),
                _scalars_result([]),  # no existing ACTIVE alerts
            ]
        )

        await _recompute_low_stock_alerts(db, JOB_ID)

        db.add.assert_called_once()
        alert = db.add.call_args[0][0]
        assert alert.product_id == inv.product_id
        assert alert.current_quantity == 2
        assert alert.threshold == 10

    @pytest.mark.asyncio
    async def test_includes_a_deduped_product_depleted_by_imported_sales(self):
        """A deduped (pre-existing) product isn't migration_id-tagged, but
        imported sales against it (Sale.migration_id == job_id) can still
        push it below threshold — scoping only to newly-created products
        would miss it entirely. The relevant-products query is a single
        UNION of both sources, not two separate queries."""
        from src.data_import.recompute import _recompute_low_stock_alerts

        deduped_product_id = uuid.uuid4()
        inv = MagicMock()
        inv.product_id = deduped_product_id
        inv.quantity_on_hand = 1
        inv.low_stock_threshold = 10

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_result([deduped_product_id]),
                _scalars_result([inv]),
                _scalars_result([]),
            ]
        )

        await _recompute_low_stock_alerts(db, JOB_ID)

        db.add.assert_called_once()
        assert db.add.call_args[0][0].product_id == deduped_product_id

    @pytest.mark.asyncio
    async def test_no_relevant_products_is_a_noop(self):
        from src.data_import.recompute import _recompute_low_stock_alerts

        db = _mock_db()
        db.execute = AsyncMock(return_value=_scalars_result([]))

        await _recompute_low_stock_alerts(db, JOB_ID)

        db.add.assert_not_called()
        # Just the one relevant-products query — nothing past it ran.
        assert db.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_skips_when_quantity_above_threshold(self):
        from src.data_import.recompute import _recompute_low_stock_alerts

        product_id = uuid.uuid4()
        inv = MagicMock()
        inv.product_id = product_id
        inv.quantity_on_hand = 50
        inv.low_stock_threshold = 10

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[_scalars_result([product_id]), _scalars_result([inv])]
        )

        await _recompute_low_stock_alerts(db, JOB_ID)

        db.add.assert_not_called()
        # Above threshold — the existing-active-alerts query never runs either.
        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_does_not_duplicate_an_existing_active_alert(self):
        from src.data_import.recompute import _recompute_low_stock_alerts

        product_id = uuid.uuid4()
        inv = MagicMock()
        inv.product_id = product_id
        inv.quantity_on_hand = 1
        inv.low_stock_threshold = 10

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_result([product_id]),
                _scalars_result([inv]),
                _scalars_result([product_id]),  # already has an ACTIVE alert
            ]
        )

        await _recompute_low_stock_alerts(db, JOB_ID)

        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_variant_level_row_below_threshold_triggers_alert(self):
        """LowStockAlert has no variant_id column, but a variant sold out by
        imported sales (_deduct_imported_sales_stock deducts at the variant
        level) must still trigger the product-level alert — checking only
        the variant_id=NULL aggregate row would miss it entirely."""
        from src.data_import.recompute import _recompute_low_stock_alerts

        product_id, variant_id = uuid.uuid4(), uuid.uuid4()
        variant_row = MagicMock()
        variant_row.product_id = product_id
        variant_row.variant_id = variant_id
        variant_row.quantity_on_hand = 0
        variant_row.low_stock_threshold = 10

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_result([product_id]),
                _scalars_result([variant_row]),
                _scalars_result([]),  # no existing ACTIVE alerts
            ]
        )

        await _recompute_low_stock_alerts(db, JOB_ID)

        db.add.assert_called_once()
        alert = db.add.call_args[0][0]
        assert alert.product_id == product_id
        assert alert.current_quantity == 0

    @pytest.mark.asyncio
    async def test_most_critical_row_used_when_multiple_rows_below_threshold(self):
        """A product with several InventoryLevel rows (aggregate + variants)
        can have more than one below its own threshold at once — only one
        alert is created per product (LowStockAlert has no variant_id to
        distinguish them), using whichever row is most depleted."""
        from src.data_import.recompute import _recompute_low_stock_alerts

        product_id = uuid.uuid4()
        variant_a, variant_b = MagicMock(), MagicMock()
        variant_a.product_id = variant_b.product_id = product_id
        variant_a.quantity_on_hand = 5
        variant_a.low_stock_threshold = 10
        variant_b.quantity_on_hand = 1
        variant_b.low_stock_threshold = 10

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_result([product_id]),
                _scalars_result([variant_a, variant_b]),
                _scalars_result([]),
            ]
        )

        await _recompute_low_stock_alerts(db, JOB_ID)

        db.add.assert_called_once()
        alert = db.add.call_args[0][0]
        assert alert.current_quantity == 1

    @pytest.mark.asyncio
    async def test_existing_active_alert_check_is_batched_not_per_item(self):
        """One query for the whole below-threshold set, not one per
        product — this step runs on every confirmed import and every
        manual /recompute retry."""
        from src.data_import.recompute import _recompute_low_stock_alerts

        product_a, product_b = uuid.uuid4(), uuid.uuid4()
        inv_a, inv_b = MagicMock(), MagicMock()
        inv_a.product_id, inv_b.product_id = product_a, product_b
        inv_a.quantity_on_hand = inv_b.quantity_on_hand = 1
        inv_a.low_stock_threshold = inv_b.low_stock_threshold = 10

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_result([product_a, product_b]),
                _scalars_result([inv_a, inv_b]),
                _scalars_result([]),
            ]
        )

        await _recompute_low_stock_alerts(db, JOB_ID)

        assert db.add.call_count == 2
        assert db.execute.await_count == 3


# ---------------------------------------------------------------------------
# _recompute_ai_signals
# ---------------------------------------------------------------------------


class TestRecomputeAiSignals:
    @pytest.mark.asyncio
    async def test_clears_pending_suggestions_then_regenerates_and_computes_prices(
        self,
    ):
        from src.data_import.recompute import _recompute_ai_signals

        product = _make_product_for_recompute()
        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(),  # delete(...) pending suggestions
                _scalars_result([product]),  # imported products (+ variants)
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
        mock_price.assert_awaited_once_with(db, product.id, variant_id=None)

    @pytest.mark.asyncio
    async def test_one_products_pricing_failure_does_not_stop_the_others(self):
        from src.data_import.recompute import _recompute_ai_signals

        product_a = _make_product_for_recompute()
        product_b = _make_product_for_recompute()
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
                        PricingSuggestionError(product_a.id, "no active lots"),
                        MagicMock(),
                    ]
                ),
            ) as mock_price,
        ):
            errors = await _recompute_ai_signals(db, BUSINESS_ID, JOB_ID)

        assert mock_price.await_count == 2
        assert len(errors) == 1
        assert errors[0]["product_id"] == str(product_a.id)

    @pytest.mark.asyncio
    async def test_reorder_suggestion_failure_does_not_block_pricing_suggestions(self):
        from src.data_import.recompute import _recompute_ai_signals

        product = _make_product_for_recompute()
        db = _mock_db()
        db.execute = AsyncMock(side_effect=[MagicMock(), _scalars_result([product])])

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

    @pytest.mark.asyncio
    async def test_a_non_pricing_exception_is_isolated_per_product_too(self):
        """compute_suggestion() can fail for reasons that aren't its own
        PricingSuggestionError (e.g. a transient FX-rate lookup failure) —
        that must still be isolated per product, not abort every remaining
        product's price suggestion."""
        from src.data_import.recompute import _recompute_ai_signals

        product_a = _make_product_for_recompute()
        product_b = _make_product_for_recompute()
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
                    side_effect=[RuntimeError("FX rate lookup timed out"), MagicMock()]
                ),
            ) as mock_price,
        ):
            errors = await _recompute_ai_signals(db, BUSINESS_ID, JOB_ID)

        assert mock_price.await_count == 2
        assert len(errors) == 1
        assert errors[0]["product_id"] == str(product_a.id)

    @pytest.mark.asyncio
    async def test_price_suggestion_call_is_wrapped_in_a_per_item_savepoint(self):
        """A real DB-level failure inside compute_suggestion() (not just a
        Python-level PricingSuggestionError) would otherwise poison the
        single SAVEPOINT the whole recompute runs inside, breaking every
        later step. Each product's call must open — and roll back to — its
        own nested SAVEPOINT. (One more begin_nested() call happens for
        the reorder-suggestion regeneration right before this — see
        TestRegenerateReorderSuggestionsForBusiness.)"""
        from src.data_import.recompute import _recompute_ai_signals

        product = _make_product_for_recompute()
        db = _mock_db()
        db.execute = AsyncMock(side_effect=[MagicMock(), _scalars_result([product])])
        db.begin_nested = MagicMock(return_value=_NestedTransaction())

        with (
            patch(
                "src.data_import.recompute.generate_reorder_suggestions",
                new=AsyncMock(return_value=[]),
            ),
            patch("src.data_import.recompute.compute_suggestion", new=AsyncMock()),
        ):
            await _recompute_ai_signals(db, BUSINESS_ID, JOB_ID)

        assert db.begin_nested.call_count == 2

    @pytest.mark.asyncio
    async def test_variant_product_computes_one_suggestion_per_variant(self):
        """A product imported with variants (task 171) must get one
        compute_suggestion() call per variant, each scoped to its own
        variant_id — calling it once with variant_id=None (as this loop
        did before task 171) would now match only untagged lots and
        silently fail for every variant-tagged import."""
        from src.data_import.recompute import _recompute_ai_signals

        variant_a_id, variant_b_id = uuid.uuid4(), uuid.uuid4()
        product = _make_product_for_recompute(variant_ids=[variant_a_id, variant_b_id])
        db = _mock_db()
        db.execute = AsyncMock(side_effect=[MagicMock(), _scalars_result([product])])

        with (
            patch(
                "src.data_import.recompute.generate_reorder_suggestions",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "src.data_import.recompute.compute_suggestion", new=AsyncMock()
            ) as mock_price,
        ):
            errors = await _recompute_ai_signals(db, BUSINESS_ID, JOB_ID)

        assert errors == []
        assert mock_price.await_count == 2
        called_variant_ids = {
            call.kwargs["variant_id"] for call in mock_price.call_args_list
        }
        assert called_variant_ids == {variant_a_id, variant_b_id}
        assert all(
            call.args == (db, product.id) for call in mock_price.call_args_list
        )

    @pytest.mark.asyncio
    async def test_variant_flagged_product_with_no_variant_rows_still_attempts_once(
        self,
    ):
        """has_variants=True with zero loaded ProductVariant rows (a data
        anomaly — e.g. every variant was later deleted) must still get one
        compute_suggestion() attempt and one accounted-for outcome, not
        silently zero calls and zero error entries. Every other product in
        this loop gets exactly this guarantee via run_isolated(); an empty
        variant_ids list would quietly break it for this one."""
        from src.data_import.recompute import _recompute_ai_signals

        product = _make_product_for_recompute(variant_ids=[])
        product.has_variants = True  # the anomaly: flagged, but no rows
        db = _mock_db()
        db.execute = AsyncMock(side_effect=[MagicMock(), _scalars_result([product])])

        with (
            patch(
                "src.data_import.recompute.generate_reorder_suggestions",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "src.data_import.recompute.compute_suggestion", new=AsyncMock()
            ) as mock_price,
        ):
            errors = await _recompute_ai_signals(db, BUSINESS_ID, JOB_ID)

        assert errors == []
        mock_price.assert_awaited_once_with(db, product.id, variant_id=None)


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
                new=AsyncMock(return_value=([], set())),
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
        """Every *independent* step must keep running when an earlier,
        unrelated one raises unexpectedly (not just a per-item error the
        step already catches itself) — the import itself has already
        committed and each of these steps operates on an independent slice
        of derived state. fifo_cogs is the one exception: it is NOT
        independent of deduct_sales_stock — when that step fails entirely
        (not a per-item failure, which returns a set of failed pairs; a
        raised exception, which leaves failed_deduction_pairs at its empty
        default), which sales actually had their stock deducted is
        unknown, so fifo_cogs must be skipped rather than run as if every
        sale succeeded."""
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
        assert any(
            e["step"] == "fifo_cogs" and "Skipped" in e["error"]
            for e in result["errors"]
        )
        m2.assert_not_awaited()
        for m in (m3, m4, m5):
            m.assert_awaited_once()
