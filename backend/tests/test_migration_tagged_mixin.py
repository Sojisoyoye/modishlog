"""Tests for MigrationTaggedMixin (task #176) — dedupes the migration_id FK
column that was hand-copied across 24 model classes in 10 domains."""

import uuid

import pytest
from sqlalchemy import ForeignKey

MIGRATION_TAGGED_MODELS = [
    ("src.auth.models", "User"),
    ("src.customers.models", "Customer"),
    ("src.expenses.models", "ExpenseCategory"),
    ("src.expenses.models", "Expense"),
    ("src.locations.models", "BusinessLocation"),
    ("src.inventory.models", "InventoryLevel"),
    ("src.inventory.models", "StockMovement"),
    ("src.inventory.models", "InventoryBatch"),
    ("src.products.models", "ProductCategory"),
    ("src.products.models", "Product"),
    ("src.products.models", "ProductVariant"),
    ("src.products.models", "PriceHistory"),
    ("src.orders.models", "PurchaseOrder"),
    ("src.orders.models", "OrderLineItem"),
    ("src.orders.models", "OrderStatusHistory"),
    ("src.orders.models", "OrderPayment"),
    ("src.orders.models", "PurchaseReturn"),
    ("src.sales.models", "Sale"),
    ("src.sales.models", "SaleAuditEntry"),
    ("src.sales.models", "SellReturn"),
    ("src.suppliers.models", "Supplier"),
    ("src.suppliers.models", "SupplierProduct"),
    ("src.stockcount.models", "StockCount"),
    ("src.stockcount.models", "StockCountItem"),
]


class TestMigrationTaggedMixin:
    def test_mixin_defines_a_nullable_indexed_fk_to_migration_jobs(self):
        # MigrationTaggedMixin is a plain mixin (no __tablename__), so its
        # column is only materialized once mixed into a real model — assert
        # against a real mixed-in model instead of the mixin directly.
        from src.customers.models import Customer

        col = Customer.__table__.columns["migration_id"]
        assert col.nullable is True
        assert col.index is True
        fk = next(iter(col.foreign_keys))
        assert fk.target_fullname == "migration_jobs.id"

    @pytest.mark.parametrize("module_path,class_name", MIGRATION_TAGGED_MODELS)
    def test_model_has_migration_id_column(self, module_path, class_name):
        """Every domain model that supports migration rollback tagging must
        still have a correctly-configured migration_id column after the
        mixin refactor — same nullable/indexed/FK-to-migration_jobs shape
        as before, just defined once instead of copy-pasted 24 times."""
        import importlib

        module = importlib.import_module(module_path)
        model = getattr(module, class_name)

        assert "migration_id" in model.__table__.columns
        col = model.__table__.columns["migration_id"]
        assert col.nullable is True
        assert col.index is True
        fk = next(iter(col.foreign_keys))
        assert fk.target_fullname == "migration_jobs.id"

    def test_migration_id_accepts_a_uuid_value(self):
        """Round-trip sanity check: assigning a UUID to migration_id on a
        mixed-in model must not raise (type mapping wired correctly)."""
        from src.customers.models import Customer

        customer = Customer(name="Test", migration_id=uuid.uuid4())
        assert customer.migration_id is not None
