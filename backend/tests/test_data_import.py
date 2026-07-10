"""Tests for the data_import ETL framework (task 162, Phase 0 foundation)."""

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

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
from src.data_import.etl.transformer import (
    IdMap,
    Transformer,
    normalize_payment_method,
)
from src.data_import.etl.validator import validate_entity_rows
from src.data_import.exceptions import InvalidJobStateError
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
    async def test_load_skips_unset_entities(self):
        db = _mock_db()
        row_counts = await loader_load(db, uuid.uuid4(), {}, IdMap())
        assert all(count == 0 for count in row_counts.values())
        db.add_all.assert_not_called()

    @pytest.mark.asyncio
    async def test_rollback_deletes_by_migration_id_in_reverse_order(self):
        db = _mock_db()
        result_mock = MagicMock(rowcount=3)
        db.execute = AsyncMock(return_value=result_mock)

        deleted_counts = await loader_rollback(db, uuid.uuid4())

        assert deleted_counts["sales"] == 3
        assert db.execute.await_count == len(deleted_counts)


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
