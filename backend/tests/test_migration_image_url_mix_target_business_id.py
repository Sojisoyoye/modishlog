"""Content test for migration aaf1881e3f19.

CI provisions a fresh Postgres service for pytest but never runs `alembic
upgrade head` against it first, so a live-DB round-trip test isn't
feasible here without also changing CI (same constraint as
test_migration_stock_adjustment_enum.py, task 167). This instead asserts
on the migration module's own upgrade() behavior directly.

Made idempotent after discovering staging and prod had `products.image_url`
backfilled via emergency raw SQL (`fix-staging.yml`/`fix-prod-schema.yml`)
before this migration ever ran through real `alembic upgrade head`
tracking — the original (non-idempotent) version failed with
DuplicateColumnError and permanently blocked every migration after it.
"""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

MIGRATION_PATH = (
    Path(__file__).parent.parent
    / "alembic"
    / "versions"
    / "aaf1881e3f19_add_missing_image_url_and_mix_target_business_id.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_aaf1881e3f19", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mock_inspector(columns=None, constraints=None, indexes=None):
    """Stand-in for sa.inspect(op.get_bind()) — columns/constraints/indexes
    are dicts of table_name -> list of names already present."""
    columns = columns or {}
    constraints = constraints or {}
    indexes = indexes or {}
    inspector = MagicMock()
    inspector.get_columns.side_effect = lambda table: [
        {"name": n} for n in columns.get(table, [])
    ]
    inspector.get_unique_constraints.side_effect = lambda table: [
        {"name": n} for n in constraints.get(table, [])
    ]
    inspector.get_foreign_keys.side_effect = lambda table: []
    inspector.get_indexes.side_effect = lambda table: [
        {"name": n} for n in indexes.get(table, [])
    ]
    return inspector


class TestImageUrlMixTargetBusinessIdMigration:
    def test_upgrade_on_a_fresh_db_adds_everything(self):
        """Original behaviour, preserved: nothing exists yet, so every
        column/FK/index/constraint gets created."""
        migration = _load_migration()

        with patch.object(migration, "op") as mock_op, patch.object(
            migration.sa, "inspect", return_value=_mock_inspector()
        ):
            migration.upgrade()

        add_column_tables = [c.args[0] for c in mock_op.add_column.call_args_list]
        assert add_column_tables == ["products", "product_mix_targets"]
        mock_op.alter_column.assert_called_once_with(
            "product_mix_targets", "business_id", nullable=False
        )
        mock_op.create_foreign_key.assert_called_once()
        mock_op.create_index.assert_called_once()
        mock_op.create_unique_constraint.assert_called_once()

    def test_upgrade_skips_image_url_when_already_backfilled(self):
        """The exact staging/prod drift scenario: products.image_url was
        added via emergency raw SQL before this migration ever ran, but
        product_mix_targets.business_id was not touched by that patch."""
        migration = _load_migration()
        inspector = _mock_inspector(columns={"products": ["image_url"]})

        with patch.object(migration, "op") as mock_op, patch.object(
            migration.sa, "inspect", return_value=inspector
        ):
            migration.upgrade()

        add_column_tables = [c.args[0] for c in mock_op.add_column.call_args_list]
        assert add_column_tables == ["product_mix_targets"]
        mock_op.create_foreign_key.assert_called_once()
        mock_op.create_index.assert_called_once()
        mock_op.create_unique_constraint.assert_called_once()

    def test_upgrade_is_a_full_noop_when_everything_already_exists(self):
        """Re-running against an already-fully-migrated DB (the normal
        idempotent-migration case) must not attempt to add or backfill
        anything a second time."""
        migration = _load_migration()
        inspector = _mock_inspector(
            columns={
                "products": ["image_url"],
                "product_mix_targets": ["business_id"],
            },
            constraints={
                "product_mix_targets": [
                    "fk_product_mix_targets_business_id",
                    "uq_mix_target_category_business",
                ]
            },
            indexes={"product_mix_targets": ["ix_product_mix_targets_business_id"]},
        )

        with patch.object(migration, "op") as mock_op, patch.object(
            migration.sa, "inspect", return_value=inspector
        ):
            migration.upgrade()

        mock_op.add_column.assert_not_called()
        mock_op.alter_column.assert_not_called()
        mock_op.execute.assert_not_called()
        mock_op.create_foreign_key.assert_not_called()
        mock_op.create_index.assert_not_called()
        mock_op.create_unique_constraint.assert_not_called()

    def test_downgrade_does_not_error(self):
        migration = _load_migration()

        with patch.object(migration, "op", MagicMock()):
            migration.downgrade()  # must not raise

    def test_revision_chain_unchanged(self):
        migration = _load_migration()

        assert migration.revision == "aaf1881e3f19"
        assert migration.down_revision == "5b084b6ad359"
