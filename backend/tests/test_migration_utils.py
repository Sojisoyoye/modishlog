"""Tests for src/core/migration_utils.py's Alembic idempotency helpers."""

from src.core import migration_utils
from tests.migration_test_utils import patched_migration_utils as _patched


class TestHasTable:
    def test_true_when_table_exists(self):
        with _patched(tables={"products"}):
            assert migration_utils.has_table("products") is True

    def test_false_when_table_missing(self):
        with _patched():
            assert migration_utils.has_table("products") is False


class TestHasColumn:
    def test_true_when_column_exists(self):
        with _patched(tables={"products"}, columns={"products": ["image_url"]}):
            assert migration_utils.has_column("products", "image_url") is True

    def test_false_when_column_missing(self):
        with _patched(tables={"products"}, columns={}):
            assert migration_utils.has_column("products", "image_url") is False

    def test_false_when_table_missing(self):
        """A missing table trivially has no columns — must not raise
        (e.g. from calling get_columns() on a nonexistent table)."""
        with _patched():
            assert migration_utils.has_column("products", "image_url") is False


class TestHasConstraint:
    def test_true_when_unique_constraint_exists(self):
        with _patched(
            tables={"product_mix_targets"},
            unique_constraints={"product_mix_targets": ["uq_mix_target"]},
        ):
            assert (
                migration_utils.has_constraint("product_mix_targets", "uq_mix_target")
                is True
            )

    def test_true_when_foreign_key_exists(self):
        with _patched(
            tables={"product_mix_targets"},
            foreign_keys={"product_mix_targets": ["fk_mix_target"]},
        ):
            assert (
                migration_utils.has_constraint("product_mix_targets", "fk_mix_target")
                is True
            )

    def test_false_when_neither_exists(self):
        with _patched(tables={"product_mix_targets"}):
            assert (
                migration_utils.has_constraint("product_mix_targets", "fk_mix_target")
                is False
            )

    def test_false_when_table_missing(self):
        with _patched():
            assert (
                migration_utils.has_constraint("product_mix_targets", "fk_mix_target")
                is False
            )


class TestHasIndex:
    def test_true_when_index_exists(self):
        with _patched(tables={"products"}, indexes={"products": ["ix_products_sku"]}):
            assert migration_utils.has_index("products", "ix_products_sku") is True

    def test_false_when_index_missing(self):
        with _patched(tables={"products"}):
            assert migration_utils.has_index("products", "ix_products_sku") is False

    def test_false_when_table_missing(self):
        with _patched():
            assert migration_utils.has_index("products", "ix_products_sku") is False
