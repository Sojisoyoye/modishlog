"""Tests for the data_import ETL framework (task 162, Phase 0 foundation)."""

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.data_import.etl.adapters.generic import GenericCSVAdapter
from src.data_import.etl.extractor import (
    CSVExtractor,
    detect_source_system,
    parse_flexible_amount,
    parse_flexible_date,
)
from src.data_import.etl.loader import load as loader_load
from src.data_import.etl.loader import rollback as loader_rollback
from src.inventory.models import InventoryLevel
from src.data_import.etl.transformer import (
    IdMap,
    Transformer,
    normalize_payment_method,
)
from src.data_import.etl.validator import validate_entity_rows
from src.data_import.exceptions import InvalidJobStateError, PurchaseOrderImportError
from src.data_import.models import (
    ExtractionMode,
    MigrationJob,
    MigrationJobStatus,
    SourceSystem,
)
from src.data_import.service import build_confirmation_snapshot, confirm_job, rollback_job

BUSINESS_ID = uuid.uuid4()
CREATED_BY = uuid.uuid4()


def _mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    return db


def _none_result():
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    return r


def _found_result(obj):
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


def _make_job(**overrides) -> MigrationJob:
    defaults = dict(
        business_id=BUSINESS_ID,
        status=MigrationJobStatus.AWAITING_CONFIRMATION,
        source_system=SourceSystem.GENERIC,
        extraction_mode=ExtractionMode.CSV,
        created_by=uuid.uuid4(),
    )
    defaults.update(overrides)
    job = MigrationJob(**defaults)
    job.id = overrides.get("id", uuid.uuid4())
    return job


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class TestParseFlexibleDate:
    def test_iso_format(self):
        assert parse_flexible_date("2026-07-10") == date(2026, 7, 10)

    def test_day_month_year(self):
        assert parse_flexible_date("25/12/2026") == date(2026, 12, 25)

    def test_day_mon_yy(self):
        assert parse_flexible_date("01-Jul-26") == date(2026, 7, 1)

    def test_unrecognised_format_raises(self):
        with pytest.raises(ValueError):
            parse_flexible_date("not-a-date")


class TestParseFlexibleAmount:
    def test_us_thousands_separator(self):
        assert parse_flexible_amount("1,200.00") == Decimal("1200.00")

    def test_european_thousands_separator(self):
        assert parse_flexible_amount("1.200,00") == Decimal("1200.00")

    def test_strips_currency_symbols(self):
        assert parse_flexible_amount("₦1,200.00") == Decimal("1200.00")
        assert parse_flexible_amount("$50.00") == Decimal("50.00")

    def test_invalid_amount_raises(self):
        with pytest.raises(Exception):
            parse_flexible_amount("not-a-number")


class TestCSVExtractor:
    @pytest.mark.asyncio
    async def test_extracts_multiple_entity_files(self):
        files = {
            "products": b"source_id,name,sku\nP1,Widget,SKU-1\n",
            "customers": b"source_id,name\nC1,Jane Doe\n",
        }
        extractor = CSVExtractor(files)
        result = await extractor.extract()

        assert result["products"] == [{"source_id": "P1", "name": "Widget", "sku": "SKU-1"}]
        assert result["customers"] == [{"source_id": "C1", "name": "Jane Doe"}]

    @pytest.mark.asyncio
    async def test_handles_bom(self):
        files = {"products": "﻿source_id,name\nP1,Widget\n".encode("utf-8")}
        extractor = CSVExtractor(files)
        result = await extractor.extract()
        assert result["products"][0]["source_id"] == "P1"


class TestDetectSourceSystem:
    def test_detects_ultimatepos(self):
        assert detect_source_system({"variation_id", "name"}) == "ultimatepos"

    def test_unknown_headers_return_none(self):
        assert detect_source_system({"foo", "bar"}) is None


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class TestValidateEntityRows:
    def test_missing_required_field_is_error(self):
        issues = validate_entity_rows("products", [{"source_id": "P1", "name": ""}])
        assert any(i.severity == "error" and i.field == "name" for i in issues)

    def test_invalid_date_is_error(self):
        rows = [
            {
                "product_source_id": "P1",
                "quantity": "1",
                "unit_price": "10.00",
                "sale_date": "not-a-date",
            }
        ]
        issues = validate_entity_rows("sales", rows)
        assert any(i.field == "sale_date" and i.severity == "error" for i in issues)

    def test_negative_amount_is_error(self):
        rows = [{"name": "Widget", "unit_cost": "-5", "selling_price": "10"}]
        issues = validate_entity_rows("products", rows)
        assert any(i.field == "unit_cost" and i.severity == "error" for i in issues)

    def test_duplicate_source_id_is_error(self):
        rows = [{"source_id": "P1", "name": "A"}, {"source_id": "P1", "name": "B"}]
        issues = validate_entity_rows("products", rows)
        assert any("Duplicate source_id" in i.message for i in issues)

    def test_valid_rows_produce_no_issues(self):
        rows = [{"source_id": "P1", "name": "Widget", "unit_cost": "5", "selling_price": "10"}]
        assert validate_entity_rows("products", rows) == []

    def test_purchase_order_missing_required_field_is_error(self):
        rows = [{"source_id": "PO1", "product_source_id": "", "quantity": "10", "unit_cost": "5"}]
        issues = validate_entity_rows("purchase_orders", rows)
        assert any(i.field == "product_source_id" and i.severity == "error" for i in issues)

    def test_purchase_order_invalid_date_is_error(self):
        rows = [
            {
                "source_id": "PO1",
                "product_source_id": "P1",
                "quantity": "10",
                "unit_cost": "5",
                "order_date": "not-a-date",
            }
        ]
        issues = validate_entity_rows("purchase_orders", rows)
        assert any(i.field == "order_date" and i.severity == "error" for i in issues)

    def test_purchase_order_negative_unit_cost_is_error(self):
        rows = [{"source_id": "PO1", "product_source_id": "P1", "quantity": "10", "unit_cost": "-5"}]
        issues = validate_entity_rows("purchase_orders", rows)
        assert any(i.field == "unit_cost" and i.severity == "error" for i in issues)

    def test_purchase_order_zero_quantity_is_error(self):
        """OrderLineItemCreate requires quantity > 0 (not just >= 0) — a
        zero value must be caught here, not surface as a raw pydantic
        error deep inside load_purchase_orders() at confirm time."""
        rows = [{"source_id": "PO1", "product_source_id": "P1", "quantity": "0", "unit_cost": "10"}]
        issues = validate_entity_rows("purchase_orders", rows)
        assert any(
            i.field == "quantity" and i.severity == "error" and "greater than zero" in i.message
            for i in issues
        )

    def test_purchase_order_zero_unit_cost_is_error(self):
        rows = [{"source_id": "PO1", "product_source_id": "P1", "quantity": "10", "unit_cost": "0"}]
        issues = validate_entity_rows("purchase_orders", rows)
        assert any(
            i.field == "unit_cost" and i.severity == "error" and "greater than zero" in i.message
            for i in issues
        )

    def test_purchase_order_decimal_and_comma_quantity_is_valid(self):
        """quantity is validated leniently (parse_flexible_amount, matching
        transform_purchase_orders()'s own parsing) — "10.0" and "1,000" must
        not be rejected here."""
        rows = [
            {"source_id": "PO1", "product_source_id": "P1", "quantity": "10.0", "unit_cost": "5"},
            {"source_id": "PO2", "product_source_id": "P1", "quantity": "1,000", "unit_cost": "5"},
        ]
        issues = validate_entity_rows("purchase_orders", rows)
        assert not any(i.field == "quantity" for i in issues)

    def test_purchase_order_fractional_quantity_is_error(self):
        """transform_purchase_orders() does int(normalize_amount(...)) on
        quantity — a genuinely fractional value like "10.7" would silently
        lose its remainder at confirm time. Must be rejected here instead."""
        rows = [{"source_id": "PO1", "product_source_id": "P1", "quantity": "10.7", "unit_cost": "5"}]
        issues = validate_entity_rows("purchase_orders", rows)
        assert any(
            i.field == "quantity" and i.severity == "error" and "whole number" in i.message
            for i in issues
        )

    def test_purchase_order_rows_sharing_source_id_are_not_flagged_as_duplicates(self):
        """Multiple rows with the same source_id are one multi-line-item
        order by design (see transform_purchase_orders) — not a duplicate,
        unlike every other entity's source_id semantics."""
        rows = [
            {"source_id": "PO1", "product_source_id": "P1", "quantity": "10", "unit_cost": "5"},
            {"source_id": "PO1", "product_source_id": "P2", "quantity": "5", "unit_cost": "10"},
        ]
        issues = validate_entity_rows("purchase_orders", rows)
        assert not any("Duplicate source_id" in i.message for i in issues)

    def test_unknown_entity_returns_no_issues(self):
        assert validate_entity_rows("not_a_real_entity", [{"anything": "x"}]) == []


# ---------------------------------------------------------------------------
# Transformer
# ---------------------------------------------------------------------------


class TestNormalizePaymentMethod:
    def test_known_variants_map_to_canonical_values(self):
        assert normalize_payment_method("Credit Card") == "card"
        assert normalize_payment_method("Bank Transfer") == "bank_transfer"

    def test_unknown_method_maps_to_other(self):
        assert normalize_payment_method("crypto") == "other"

    def test_none_returns_none(self):
        assert normalize_payment_method(None) is None


class TestIdMap:
    def test_register_and_lookup(self):
        id_map = IdMap()
        internal_id = uuid.uuid4()
        id_map.register("products", "P1", internal_id)
        assert id_map.lookup("products", "P1") == internal_id

    def test_lookup_miss_returns_none(self):
        assert IdMap().lookup("products", "unknown") is None


class TestTransformerDedup:
    @pytest.mark.asyncio
    async def test_dedup_customer_matches_by_email(self):
        existing = MagicMock(id=uuid.uuid4(), email="jane@example.com")
        db = _mock_db()
        db.execute = AsyncMock(return_value=_found_result(existing))

        transformer = Transformer(db, BUSINESS_ID, CREATED_BY)
        result = await transformer.dedup_customer("jane@example.com", None)
        assert result is existing

    @pytest.mark.asyncio
    async def test_dedup_product_prefers_barcode_over_sku(self):
        existing = MagicMock(id=uuid.uuid4())
        db = _mock_db()
        db.execute = AsyncMock(return_value=_found_result(existing))

        transformer = Transformer(db, BUSINESS_ID, CREATED_BY)
        result = await transformer.dedup_product("123456", "SKU-1")
        assert result is existing
        # Only the barcode lookup should have run — sku lookup short-circuits.
        assert db.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_dedup_product_barcode_lookup_is_scoped_to_business_id(self):
        """A barcode match from another business must never leak into this
        job's id_map — barcode has no global-uniqueness constraint."""
        db = _mock_db()
        db.execute = AsyncMock(return_value=_none_result())
        transformer = Transformer(db, BUSINESS_ID, CREATED_BY)

        await transformer.dedup_product("123456", None)

        executed_query = db.execute.call_args_list[0].args[0]
        compiled = str(executed_query.compile(compile_kwargs={"literal_binds": False}))
        assert "business_id" in compiled


class TestTransformProducts:
    @pytest.mark.asyncio
    async def test_new_product_is_normalised_and_gets_a_pre_assigned_id(self):
        db = _mock_db()
        db.execute = AsyncMock(return_value=_none_result())
        transformer = Transformer(db, BUSINESS_ID, CREATED_BY)

        rows = [
            {
                "source_id": "P1",
                "name": "Ankara Fabric",
                "unit_cost": "1,200.00",
                "selling_price": "2,000.00",
            }
        ]
        result = await transformer.transform_products(rows)

        assert len(result) == 1
        assert result[0]["unit_cost"] == Decimal("1200.000000")
        assert result[0]["slug"] == "ankara-fabric"
        assert result[0]["id"] == transformer.id_map.lookup("products", "P1")

    @pytest.mark.asyncio
    async def test_deduped_product_is_excluded_from_output(self):
        existing = MagicMock(id=uuid.uuid4())
        db = _mock_db()
        db.execute = AsyncMock(return_value=_found_result(existing))
        transformer = Transformer(db, BUSINESS_ID, CREATED_BY)

        result = await transformer.transform_products(
            [{"source_id": "P1", "name": "Existing", "barcode": "123"}]
        )
        assert result == []
        assert transformer.id_map.lookup("products", "P1") == existing.id


class TestGhostProducts:
    @pytest.mark.asyncio
    async def test_sale_referencing_missing_product_gets_ghost_and_resolves(self):
        db = _mock_db()
        db.execute = AsyncMock(return_value=_none_result())
        transformer = Transformer(db, BUSINESS_ID, CREATED_BY)

        sales_raw = [
            {
                "product_source_id": "GONE-1",
                "product_name": "Old Fabric",
                "quantity": "2",
                "unit_price": "500",
                "sale_date": "2026-01-01",
            }
        ]
        ghosts = transformer.detect_ghost_products(sales_raw, known_product_source_ids=set())
        assert len(ghosts) == 1
        assert ghosts[0]["name"] == "[Deleted Product: Old Fabric]"
        assert any(w.severity == "warning" for w in transformer.warnings)

        products = await transformer.transform_products(ghosts)
        assert len(products) == 1

        sales = transformer.transform_sales(sales_raw)
        assert len(sales) == 1
        assert sales[0]["product_id"] == products[0]["id"]

    def test_sale_with_unresolvable_product_is_dropped_with_error(self):
        transformer = Transformer(_mock_db(), BUSINESS_ID, CREATED_BY)
        sales_raw = [
            {
                "product_source_id": "UNKNOWN",
                "quantity": "1",
                "unit_price": "10",
                "sale_date": "2026-01-01",
            }
        ]
        result = transformer.transform_sales(sales_raw)
        assert result == []
        assert any(w.severity == "error" for w in transformer.warnings)

    def test_sale_with_unparseable_quantity_is_dropped_not_raised(self):
        """Malformed quantity must never crash transform — validator hasn't
        had a chance to reject it yet when this runs (transform is called
        before validate_extracted_data in the pipeline)."""
        id_map = IdMap()
        product_id = uuid.uuid4()
        id_map.register("products", "P1", product_id)
        transformer = Transformer(_mock_db(), BUSINESS_ID, CREATED_BY, id_map)

        sales_raw = [
            {
                "product_source_id": "P1",
                "quantity": "five",
                "unit_price": "10",
                "sale_date": "2026-01-01",
            }
        ]
        result = transformer.transform_sales(sales_raw)
        assert result == []
        assert any(w.severity == "error" for w in transformer.warnings)


class TestTransformCategories:
    @pytest.mark.asyncio
    async def test_child_resolves_parent_within_same_batch(self):
        transformer = Transformer(_mock_db(), BUSINESS_ID, CREATED_BY)
        rows = [
            {"source_id": "C1", "name": "Fabrics"},
            {"source_id": "C2", "name": "Ankara", "parent_source_id": "C1"},
        ]
        result = await transformer.transform_categories(rows)
        assert result[1]["parent_id"] == result[0]["id"]


class TestTransformPurchaseOrders:
    def _transformer_with_product(self, product_source_id="P1"):
        transformer = Transformer(_mock_db(), BUSINESS_ID, CREATED_BY)
        product_id = uuid.uuid4()
        transformer.id_map.register("products", product_source_id, product_id)
        return transformer, product_id

    def test_rows_sharing_source_id_group_into_one_order_with_two_line_items(self):
        transformer, product_id = self._transformer_with_product("P1")
        transformer.id_map.register("products", "P2", uuid.uuid4())
        rows = [
            {
                "source_id": "PO1",
                "supplier_name": "Acme Textiles",
                "product_source_id": "P1",
                "quantity": "10",
                "unit_cost": "500",
                "order_date": "2026-01-01",
            },
            {
                "source_id": "PO1",
                "supplier_name": "Acme Textiles",
                "product_source_id": "P2",
                "quantity": "5",
                "unit_cost": "200",
                "order_date": "2026-01-01",
            },
        ]
        result = transformer.transform_purchase_orders(rows)

        assert len(result) == 1
        assert result[0]["supplier_name"] == "Acme Textiles"
        assert len(result[0]["line_items"]) == 2
        assert result[0]["line_items"][0]["product_id"] == product_id
        assert result[0]["line_items"][0]["quantity"] == 10
        assert result[0]["line_items"][0]["unit_cost"] == Decimal("500.000000")

    def test_missing_order_date_produces_warning(self):
        """load_purchase_orders() passes order_date straight through as the
        DELIVERED transition's actual_delivery_date; transition_status()
        falls back to date.today() when it's None, silently backdating a
        historical import. Must warn, not silently proceed."""
        transformer, product_id = self._transformer_with_product("P1")
        rows = [
            {
                "source_id": "PO1",
                "supplier_name": "Acme Textiles",
                "product_source_id": "P1",
                "quantity": "10",
                "unit_cost": "500",
            }
        ]
        result = transformer.transform_purchase_orders(rows)

        assert len(result) == 1
        assert result[0]["order_date"] is None
        assert any(
            w.field == "order_date" and w.severity == "warning"
            for w in transformer.warnings
        )

    def test_order_level_fields_backfilled_from_a_later_row_in_the_group(self):
        """order_date/fx_rate/currency/supplier/location are order-level,
        but a business's export may only populate them on whichever line
        row happened to carry the value — not necessarily the first one.
        A later row filling in what an earlier row left blank must not be
        silently discarded (previously only the first row was ever
        consulted for these fields)."""
        transformer, product_id = self._transformer_with_product("P1")
        transformer.id_map.register("products", "P2", uuid.uuid4())
        rows = [
            {
                "source_id": "PO1",
                "supplier_name": "Acme Textiles",
                "product_source_id": "P1",
                "quantity": "10",
                "unit_cost": "500",
                # order_date/fx_rate/currency all blank on this row.
            },
            {
                "source_id": "PO1",
                "supplier_name": "Acme Textiles",
                "product_source_id": "P2",
                "quantity": "5",
                "unit_cost": "200",
                "order_date": "2025-03-01",
                "fx_rate": "1550",
                "currency": "ngn",
            },
        ]
        result = transformer.transform_purchase_orders(rows)

        assert len(result) == 1
        assert result[0]["order_date"] == date(2025, 3, 1)
        assert result[0]["fx_rate"] == Decimal("1550.000000")
        assert result[0]["currency"] == "NGN"
        assert not any(w.field == "order_date" for w in transformer.warnings)

    def test_distinct_source_ids_produce_separate_orders(self):
        transformer, product_id = self._transformer_with_product("P1")
        rows = [
            {"source_id": "PO1", "supplier_name": "A", "product_source_id": "P1", "quantity": "1", "unit_cost": "10"},
            {"source_id": "PO2", "supplier_name": "B", "product_source_id": "P1", "quantity": "1", "unit_cost": "10"},
        ]
        result = transformer.transform_purchase_orders(rows)
        assert len(result) == 2

    def test_resolves_supplier_id_from_id_map(self):
        transformer, product_id = self._transformer_with_product("P1")
        supplier_id = uuid.uuid4()
        transformer.id_map.register("suppliers", "S1", supplier_id)
        rows = [
            {
                "source_id": "PO1",
                "supplier_source_id": "S1",
                "supplier_name": "Acme",
                "product_source_id": "P1",
                "quantity": "1",
                "unit_cost": "10",
            }
        ]
        result = transformer.transform_purchase_orders(rows)
        assert result[0]["supplier_id"] == supplier_id

    def test_missing_supplier_name_falls_back_to_source_id(self):
        transformer, product_id = self._transformer_with_product("P1")
        rows = [
            {"source_id": "PO1", "product_source_id": "P1", "quantity": "1", "unit_cost": "10"},
        ]
        result = transformer.transform_purchase_orders(rows)
        assert result[0]["supplier_name"] == "PO1"

    def test_row_with_unresolvable_product_is_dropped_with_error(self):
        transformer = Transformer(_mock_db(), BUSINESS_ID, CREATED_BY)
        rows = [
            {"source_id": "PO1", "supplier_name": "A", "product_source_id": "UNKNOWN", "quantity": "1", "unit_cost": "10"},
        ]
        result = transformer.transform_purchase_orders(rows)
        assert result == []
        assert any(w.severity == "error" for w in transformer.warnings)

    def test_order_with_some_resolvable_and_some_unresolvable_lines_keeps_resolvable_ones(self):
        transformer, product_id = self._transformer_with_product("P1")
        rows = [
            {"source_id": "PO1", "supplier_name": "A", "product_source_id": "P1", "quantity": "1", "unit_cost": "10"},
            {"source_id": "PO1", "supplier_name": "A", "product_source_id": "UNKNOWN", "quantity": "1", "unit_cost": "10"},
        ]
        result = transformer.transform_purchase_orders(rows)
        assert len(result) == 1
        assert len(result[0]["line_items"]) == 1

    def test_unparseable_quantity_drops_row_with_error_not_raised(self):
        transformer, product_id = self._transformer_with_product("P1")
        rows = [
            {"source_id": "PO1", "supplier_name": "A", "product_source_id": "P1", "quantity": "many", "unit_cost": "10"},
        ]
        result = transformer.transform_purchase_orders(rows)
        assert result == []
        assert any(w.severity == "error" for w in transformer.warnings)

    def test_fx_rate_is_parsed_onto_the_group(self):
        transformer, product_id = self._transformer_with_product("P1")
        rows = [
            {
                "source_id": "PO1",
                "supplier_name": "A",
                "product_source_id": "P1",
                "quantity": "10",
                "unit_cost": "500",
                "fx_rate": "1620.50",
            },
        ]
        result = transformer.transform_purchase_orders(rows)
        assert result[0]["fx_rate"] == Decimal("1620.500000")

    def test_missing_fx_rate_is_none_not_a_default(self):
        transformer, product_id = self._transformer_with_product("P1")
        rows = [
            {"source_id": "PO1", "supplier_name": "A", "product_source_id": "P1", "quantity": "10", "unit_cost": "500"},
        ]
        result = transformer.transform_purchase_orders(rows)
        assert result[0]["fx_rate"] is None

    def test_decimal_and_comma_quantity_parse_instead_of_being_dropped(self):
        """validate_entity_rows() accepts "10.0"/"1,000" for quantity (it
        validates via the same lenient parse_flexible_amount() as every
        other amount field) — a strict int(row["quantity"]) here would
        reject what validation just accepted, silently dropping the line
        item at confirm time on a row the user was told was valid."""
        transformer, product_id = self._transformer_with_product("P1")
        rows = [
            {"source_id": "PO1", "supplier_name": "A", "product_source_id": "P1", "quantity": "10.0", "unit_cost": "5", "order_date": "2024-01-01"},
            {"source_id": "PO2", "supplier_name": "A", "product_source_id": "P1", "quantity": "1,000", "unit_cost": "5", "order_date": "2024-01-02"},
        ]
        result = transformer.transform_purchase_orders(rows)
        assert len(result) == 2
        assert result[0]["line_items"][0]["quantity"] == 10
        assert result[1]["line_items"][0]["quantity"] == 1000
        assert not transformer.warnings


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


class TestLoader:
    @pytest.mark.asyncio
    async def test_load_tags_every_row_with_migration_id_and_counts_rows(self):
        db = _mock_db()
        migration_id = uuid.uuid4()
        id_map = IdMap()

        product_id = uuid.uuid4()
        transformed = {
            "products": [
                {
                    "id": product_id,
                    "name": "Widget",
                    "sku": "SKU-1",
                    "slug": "widget",
                    "unit_cost": Decimal("5"),
                    "selling_price": Decimal("10"),
                    "currency": "NGN",
                    "business_id": BUSINESS_ID,
                }
            ]
        }

        row_counts = await loader_load(db, migration_id, transformed, id_map)

        assert row_counts["products"] == 1
        assert row_counts["sales"] == 0
        added_product = db.add_all.call_args_list[0].args[0][0]
        assert added_product.migration_id == migration_id
        assert added_product.id == product_id

    @pytest.mark.asyncio
    async def test_load_initializes_zeroed_inventory_level_for_every_new_product(self):
        """adjust_stock() (called by transition_status() during purchase-order
        delivery) requires an existing InventoryLevel row — it's an UPDATE,
        not an upsert — so every imported product needs one created up front,
        same as create_product() -> initialize_inventory() does for products
        created through the normal (non-import) flow."""
        db = _mock_db()
        migration_id = uuid.uuid4()
        product_id = uuid.uuid4()
        transformed = {
            "products": [
                {
                    "id": product_id,
                    "name": "Widget",
                    "sku": "SKU-1",
                    "slug": "widget",
                    "unit_cost": Decimal("5"),
                    "selling_price": Decimal("10"),
                    "currency": "NGN",
                    "business_id": BUSINESS_ID,
                }
            ]
        }

        await loader_load(db, migration_id, transformed, IdMap())

        inventory_calls = [
            call.args[0]
            for call in db.add_all.call_args_list
            if call.args[0] and isinstance(call.args[0][0], InventoryLevel)
        ]
        assert len(inventory_calls) == 1
        inventory_rows = inventory_calls[0]
        assert len(inventory_rows) == 1
        assert inventory_rows[0].product_id == product_id
        assert inventory_rows[0].variant_id is None
        assert inventory_rows[0].quantity_on_hand == 0
        assert inventory_rows[0].migration_id == migration_id
        # Matches initialize_inventory()'s own explicit default — passed
        # explicitly here too, not left to the column default, so the two
        # construction sites can't silently drift apart.
        assert inventory_rows[0].low_stock_threshold == 10

    @pytest.mark.asyncio
    async def test_load_skips_unset_entities(self):
        db = _mock_db()
        row_counts = await loader_load(db, uuid.uuid4(), {}, IdMap())
        assert all(count == 0 for count in row_counts.values())
        db.add_all.assert_not_called()

    @pytest.mark.asyncio
    async def test_rollback_deletes_by_migration_id_in_reverse_order(self):
        db = _mock_db()
        result_mock = MagicMock(rowcount=3)
        empty_scalars = MagicMock()
        empty_scalars.scalars.return_value.all.return_value = []
        # First call is the pre-flight PurchaseOrder-id lookup (empty here —
        # no purchase orders in this import, so the payment-block check is
        # skipped) — every remaining call is one of the FK-ordered deletes.
        db.execute = AsyncMock(side_effect=[empty_scalars] + [result_mock] * 20)

        deleted_counts = await loader_rollback(db, uuid.uuid4())

        assert deleted_counts["sales"] == 3
        assert db.execute.await_count == len(deleted_counts) + 1

    @pytest.mark.asyncio
    async def test_rollback_blocked_when_imported_po_has_a_payment_recorded(self):
        """A payment recorded against an imported PO after the import isn't
        part of the import (the loader never creates OrderPayment rows) —
        deleting the PurchaseOrder would violate the order_payments FK (no
        ON DELETE CASCADE) or silently destroy that real payment. Rollback
        must refuse before deleting anything."""
        from src.data_import.exceptions import PurchaseOrderRollbackBlockedError

        db = _mock_db()
        po_id = uuid.uuid4()
        blocked_result = MagicMock()
        blocked_result.scalars.return_value.all.return_value = [po_id]
        db.execute = AsyncMock(return_value=blocked_result)

        with pytest.raises(PurchaseOrderRollbackBlockedError):
            await loader_rollback(db, uuid.uuid4())

        # Refused before any delete statement was issued.
        assert db.execute.await_count == 1


class TestLoadPurchaseOrders:
    """load_purchase_orders() orchestrates create_order()/transition_status()
    (already tested in test_orders.py) rather than reimplementing inventory
    writes — these tests mock those two collaborators and verify the
    orchestration: right OrderCreate shape, full delivery-chain transition,
    and migration_id tagging."""

    def _empty_scalars(self):
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        return r

    @pytest.mark.asyncio
    async def test_creates_zeroed_inventory_level_for_deduped_product_missing_one(self):
        """A PO line item can reference a *deduped* (pre-existing) product,
        not one this loader just created — nothing guarantees that product
        already has an InventoryLevel row (see load()'s own comment). If it
        doesn't, adjust_stock() (inside transition_status()) raises
        ProductStockNotFoundError and aborts the whole import batch, not
        just this one order."""
        from src.data_import.etl.loader import load_purchase_orders

        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_order.line_items = [MagicMock()]
        product_id = uuid.uuid4()

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                self._empty_scalars(),  # InventoryLevel existence check -> none found
                self._empty_scalars(),  # InventoryBatch tag sweep
                self._empty_scalars(),  # StockMovement tag sweep
                self._empty_scalars(),  # OrderStatusHistory tag sweep
            ]
        )

        with (
            patch("src.data_import.etl.loader.create_order", new=AsyncMock(return_value=mock_order)),
            patch("src.data_import.etl.loader.transition_status", new=AsyncMock(return_value=mock_order)),
        ):
            await load_purchase_orders(
                db, uuid.uuid4(), BUSINESS_ID, CREATED_BY,
                po_groups=[
                    {
                        "source_id": "PO1",
                        "supplier_name": "Acme",
                        "line_items": [
                            {"product_id": product_id, "variant_id": None, "quantity": 10, "unit_cost": Decimal("5")}
                        ],
                    }
                ],
            )

        inventory_calls = [
            call.args[0]
            for call in db.add_all.call_args_list
            if call.args[0] and isinstance(call.args[0][0], InventoryLevel)
        ]
        assert len(inventory_calls) == 1
        assert inventory_calls[0][0].product_id == product_id
        assert inventory_calls[0][0].quantity_on_hand == 0
        # Untagged — this product isn't newly created by this import, so it
        # must not be deleted on rollback (unlike load()'s InventoryLevel
        # rows for genuinely new products).
        assert inventory_calls[0][0].migration_id is None

    @pytest.mark.asyncio
    async def test_creates_order_and_transitions_through_full_delivery_chain(self):
        from src.data_import.etl.loader import load_purchase_orders

        migration_id = uuid.uuid4()
        product_id = uuid.uuid4()

        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_line_item = MagicMock()
        mock_order.line_items = [mock_line_item]

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[
                self._empty_scalars(),  # InventoryLevel existence check (pre-loop)
                self._empty_scalars(),  # InventoryBatch tag sweep
                self._empty_scalars(),  # StockMovement tag sweep
                self._empty_scalars(),  # OrderStatusHistory tag sweep
            ]
        )

        with (
            patch("src.data_import.etl.loader.create_order", new=AsyncMock(return_value=mock_order)) as mock_create,
            patch("src.data_import.etl.loader.transition_status", new=AsyncMock(return_value=mock_order)) as mock_transition,
        ):
            count = await load_purchase_orders(
                db,
                migration_id,
                BUSINESS_ID,
                CREATED_BY,
                po_groups=[
                    {
                        "source_id": "PO1",
                        "supplier_name": "Acme",
                        "supplier_id": None,
                        "location_id": None,
                        "order_date": date(2026, 1, 1),
                        "currency": "USD",
                        "fx_rate": Decimal("1620.50"),
                        "line_items": [
                            {"product_id": product_id, "variant_id": None, "quantity": 10, "unit_cost": Decimal("5")}
                        ],
                    }
                ],
            )

        assert count == 1
        mock_create.assert_awaited_once()
        order_create_arg = mock_create.await_args.args[1]
        assert order_create_arg.supplier_name == "Acme"
        assert order_create_arg.is_purchase_order is False
        assert order_create_arg.fx_rate_at_creation == Decimal("1620.50")
        assert len(order_create_arg.line_items) == 1
        assert order_create_arg.line_items[0].product_id == product_id

        assert mock_transition.await_count == 4
        transitioned_statuses = [call.args[2].new_status for call in mock_transition.await_args_list]
        assert transitioned_statuses == ["IN_PRODUCTION", "SHIPPING", "CLEARED", "DELIVERED"]
        final_transition = mock_transition.await_args_list[-1].args[2]
        assert final_transition.actual_delivery_date == date(2026, 1, 1)

        assert mock_order.migration_id == migration_id
        assert mock_line_item.migration_id == migration_id

    @pytest.mark.asyncio
    async def test_groups_with_no_resolvable_line_items_are_skipped(self):
        from src.data_import.etl.loader import load_purchase_orders

        db = _mock_db()
        with (
            patch("src.data_import.etl.loader.create_order", new=AsyncMock()) as mock_create,
            patch("src.data_import.etl.loader.transition_status", new=AsyncMock()),
        ):
            count = await load_purchase_orders(
                db, uuid.uuid4(), BUSINESS_ID, CREATED_BY,
                po_groups=[{"source_id": "PO1", "supplier_name": "A", "line_items": []}],
            )

        assert count == 0
        mock_create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tag_sweep_queries_are_batched_not_per_order(self):
        """3 sweep queries total (InventoryBatch/StockMovement/
        OrderStatusHistory), regardless of how many orders were created —
        not 3 per order."""
        from src.data_import.etl.loader import load_purchase_orders

        order_a, order_b = MagicMock(), MagicMock()
        order_a.id, order_b.id = uuid.uuid4(), uuid.uuid4()
        order_a.line_items, order_b.line_items = [MagicMock()], [MagicMock()]
        product_a, product_b = uuid.uuid4(), uuid.uuid4()

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[self._empty_scalars() for _ in range(4)])

        with (
            patch(
                "src.data_import.etl.loader.create_order",
                new=AsyncMock(side_effect=[order_a, order_b]),
            ),
            patch(
                "src.data_import.etl.loader.transition_status",
                new=AsyncMock(side_effect=[order_a] * 4 + [order_b] * 4),
            ),
        ):
            count = await load_purchase_orders(
                db, uuid.uuid4(), BUSINESS_ID, CREATED_BY,
                po_groups=[
                    {
                        "source_id": "PO1",
                        "supplier_name": "A",
                        "line_items": [
                            {"product_id": product_a, "variant_id": None, "quantity": 1, "unit_cost": Decimal("5")}
                        ],
                    },
                    {
                        "source_id": "PO2",
                        "supplier_name": "B",
                        "line_items": [
                            {"product_id": product_b, "variant_id": None, "quantity": 1, "unit_cost": Decimal("5")}
                        ],
                    },
                ],
            )

        assert count == 2
        # 1 InventoryLevel existence check + 3 batched sweeps = 4, not
        # 1 + (3 x 2 orders) = 7.
        assert db.execute.await_count == 4

    @pytest.mark.asyncio
    async def test_create_order_error_propagates_without_being_swallowed(self):
        """A product referenced by a line item can be deleted between
        validation and confirm — create_order() raises OrderLineItemError in
        that case. The loader must not swallow it (the caller's
        request-scoped transaction is what rolls the whole import back)."""
        from src.orders.exceptions import OrderLineItemError

        from src.data_import.etl.loader import load_purchase_orders

        db = _mock_db()
        db.execute = AsyncMock(return_value=self._empty_scalars())
        product_id = uuid.uuid4()

        with (
            patch(
                "src.data_import.etl.loader.create_order",
                new=AsyncMock(side_effect=OrderLineItemError(None, [product_id])),
            ),
            patch("src.data_import.etl.loader.transition_status", new=AsyncMock()) as mock_transition,
        ):
            with pytest.raises(OrderLineItemError):
                await load_purchase_orders(
                    db, uuid.uuid4(), BUSINESS_ID, CREATED_BY,
                    po_groups=[
                        {
                            "source_id": "PO1",
                            "supplier_name": "Acme",
                            "line_items": [
                                {"product_id": product_id, "variant_id": None, "quantity": 1, "unit_cost": Decimal("5")}
                            ],
                        }
                    ],
                )

        mock_transition.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_transition_status_error_mid_chain_propagates(self):
        """A failure partway through the 4-step delivery chain (e.g. a
        concurrent modification) must not be swallowed either."""
        from src.orders.exceptions import InvalidStatusTransitionError

        from src.data_import.etl.loader import load_purchase_orders

        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_order.line_items = [MagicMock()]
        product_id = uuid.uuid4()

        db = _mock_db()
        db.execute = AsyncMock(return_value=self._empty_scalars())
        with (
            patch("src.data_import.etl.loader.create_order", new=AsyncMock(return_value=mock_order)),
            patch(
                "src.data_import.etl.loader.transition_status",
                new=AsyncMock(
                    side_effect=[
                        mock_order,
                        InvalidStatusTransitionError(mock_order.id, "SHIPPING", "CLEARED", []),
                    ]
                ),
            ) as mock_transition,
        ):
            with pytest.raises(InvalidStatusTransitionError):
                await load_purchase_orders(
                    db, uuid.uuid4(), BUSINESS_ID, CREATED_BY,
                    po_groups=[
                        {
                            "source_id": "PO1",
                            "supplier_name": "Acme",
                            "line_items": [
                                {"product_id": product_id, "variant_id": None, "quantity": 1, "unit_cost": Decimal("5")}
                            ],
                        }
                    ],
                )

        assert mock_transition.await_count == 2


# ---------------------------------------------------------------------------
# Generic adapter
# ---------------------------------------------------------------------------


class TestGenericAdapter:
    def test_passthrough_returns_row_unchanged(self):
        adapter = GenericCSVAdapter()
        row = {"source_id": "P1", "name": "Widget"}
        assert adapter.map_row("products", row) is row


# ---------------------------------------------------------------------------
# Confirmation-snapshot gate — status flow (subtask 162.2)
# ---------------------------------------------------------------------------


class TestConfirmationGate:
    @pytest.mark.asyncio
    async def test_confirm_before_awaiting_confirmation_raises_invalid_state(self):
        job = _make_job(status=MigrationJobStatus.PENDING)
        with pytest.raises(InvalidJobStateError):
            await confirm_job(_mock_db(), job, approved=True)

    @pytest.mark.asyncio
    async def test_confirmation_snapshot_before_awaiting_confirmation_raises(self):
        job = _make_job(status=MigrationJobStatus.PENDING)
        with pytest.raises(InvalidJobStateError):
            await build_confirmation_snapshot(_mock_db(), job)

    @pytest.mark.asyncio
    async def test_confirm_declined_cancels_without_loading(self):
        job = _make_job(status=MigrationJobStatus.AWAITING_CONFIRMATION)
        db = _mock_db()
        result = await confirm_job(db, job, approved=False)
        assert result.status == MigrationJobStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_rollback_requires_done_status(self):
        job = _make_job(status=MigrationJobStatus.AWAITING_CONFIRMATION)
        with pytest.raises(InvalidJobStateError):
            await rollback_job(_mock_db(), job)

    @pytest.mark.asyncio
    async def test_purchase_order_import_errors_are_translated_to_one_domain_exception(self):
        """load_purchase_orders() reuses orders/inventory services unmodified
        and can raise any of their exception types — confirm_job() must
        translate every one of them into this domain's own
        PurchaseOrderImportError, so callers (the router) only need to know
        about one exception type, not every domain those services touch."""
        from src.orders.exceptions import OrderLineItemError

        job = _make_job(status=MigrationJobStatus.AWAITING_CONFIRMATION)
        db = _mock_db()

        with (
            patch(
                "src.data_import.service._extract_and_transform",
                new=AsyncMock(return_value=({}, {"purchase_orders": []}, MagicMock(id_map=IdMap()))),
            ),
            patch("src.data_import.service.loader_load", new=AsyncMock(return_value={})),
            patch(
                "src.data_import.service.loader_load_purchase_orders",
                new=AsyncMock(side_effect=OrderLineItemError(None, [uuid.uuid4()])),
            ),
        ):
            with pytest.raises(PurchaseOrderImportError):
                await confirm_job(db, job, approved=True)

    @pytest.mark.asyncio
    async def test_purchase_order_import_error_does_not_leak_cause_text(self):
        """A pydantic ValidationError's str() includes field paths, input
        values, and an errors.pydantic.dev URL — none of that belongs in an
        HTTP response (this codebase already did a dedicated security pass,
        PR #222, to stop str(e) leaking internals to clients). The raw
        cause must stay on `.cause` for server-side logging only; the
        exception's own message must be a fixed, safe string."""
        from pydantic import BaseModel

        class _Model(BaseModel):
            quantity: int

        try:
            _Model(quantity="not-a-number")
        except Exception as pydantic_error:
            cause = pydantic_error

        job = _make_job(status=MigrationJobStatus.AWAITING_CONFIRMATION)
        db = _mock_db()

        with (
            patch(
                "src.data_import.service._extract_and_transform",
                new=AsyncMock(return_value=({}, {"purchase_orders": []}, MagicMock(id_map=IdMap()))),
            ),
            patch("src.data_import.service.loader_load", new=AsyncMock(return_value={})),
            patch(
                "src.data_import.service.loader_load_purchase_orders",
                new=AsyncMock(side_effect=cause),
            ),
        ):
            with pytest.raises(PurchaseOrderImportError) as exc_info:
                await confirm_job(db, job, approved=True)

        assert "not-a-number" not in str(exc_info.value)
        assert "pydantic.dev" not in str(exc_info.value)
        assert exc_info.value.cause is cause


# ---------------------------------------------------------------------------
# Router — confirm endpoint 409 gate
# ---------------------------------------------------------------------------


class TestConfirmEndpoint:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from src.main import app

        self.app = app
        self._orig = app.dependency_overrides.copy()
        yield
        app.dependency_overrides = self._orig

    def _override(self, db, job):
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        from src.auth.models import User
        from src.core.database import get_db

        async def _fake_db():
            yield db

        user = MagicMock(spec=User)
        user.id = uuid.uuid4()

        self.app.dependency_overrides[get_db] = _fake_db
        self.app.dependency_overrides[get_current_active_user] = lambda: user
        self.app.dependency_overrides[get_current_business_id] = lambda: job.business_id

    def test_confirm_returns_409_when_job_not_awaiting_confirmation(self):
        job = _make_job(status=MigrationJobStatus.PENDING)
        db = _mock_db()
        db.execute = AsyncMock(return_value=_found_result(job))
        self._override(db, job)

        with TestClient(self.app) as client:
            resp = client.post(
                f"/api/v1/import/jobs/{job.id}/confirm", json={"approved": True}
            )
        assert resp.status_code == 409
