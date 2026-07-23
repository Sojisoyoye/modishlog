"""Content test for ad3a7417f748 (fix_inventory_levels_unique_constraint),
hardened for idempotency after code review flagged it as the one migration
in the task-165/171 window left unguarded against alembic_version drift —
see src/core/migration_utils.py's docstring for the incident class this
guards against, and test_migration_variant_and_consumption_idempotency.py
for the sibling migrations already covered this way.
"""

from tests.migration_test_utils import load_migration
from tests.migration_test_utils import patched_migration_utils as _patched

FILENAME = "ad3a7417f748_fix_inventory_levels_unique_constraint.py"


class TestInventoryLevelsUniqueConstraintMigration:
    def test_fresh_db_drops_old_constraint_and_adds_both_indexes(self):
        migration = load_migration(FILENAME)

        with _patched(
            migration,
            tables={"inventory_levels"},
            unique_constraints={
                "inventory_levels": ["inventory_levels_product_id_key"]
            },
        ) as mock_op:
            migration.upgrade()

        mock_op.drop_constraint.assert_called_once_with(
            "inventory_levels_product_id_key", "inventory_levels", type_="unique"
        )
        assert mock_op.create_index.call_count == 2

    def test_full_noop_when_already_migrated(self):
        migration = load_migration(FILENAME)

        with _patched(
            migration,
            tables={"inventory_levels"},
            indexes={
                "inventory_levels": [
                    "uq_inventory_levels_product_no_variant",
                    "uq_inventory_levels_product_variant",
                ]
            },
        ) as mock_op:
            migration.upgrade()

        mock_op.drop_constraint.assert_not_called()
        mock_op.create_index.assert_not_called()

    def test_upgrade_adds_only_the_missing_index_when_partially_applied(self):
        """The exact drift scenario this hardening targets: a prior attempt
        dropped the old constraint and created one index before failing —
        re-running must not re-attempt the drop and must add only the
        still-missing index."""
        migration = load_migration(FILENAME)

        with _patched(
            migration,
            tables={"inventory_levels"},
            indexes={"inventory_levels": ["uq_inventory_levels_product_no_variant"]},
        ) as mock_op:
            migration.upgrade()

        mock_op.drop_constraint.assert_not_called()
        mock_op.create_index.assert_called_once()
        assert (
            mock_op.create_index.call_args.args[0]
            == "uq_inventory_levels_product_variant"
        )

    def test_downgrade_fresh_recreates_constraint_and_drops_both_indexes(self):
        migration = load_migration(FILENAME)

        with _patched(
            migration,
            tables={"inventory_levels"},
            indexes={
                "inventory_levels": [
                    "uq_inventory_levels_product_no_variant",
                    "uq_inventory_levels_product_variant",
                ]
            },
        ) as mock_op:
            migration.downgrade()

        assert mock_op.drop_index.call_count == 2
        mock_op.create_unique_constraint.assert_called_once_with(
            "inventory_levels_product_id_key", "inventory_levels", ["product_id"]
        )

    def test_downgrade_noop_when_already_downgraded(self):
        migration = load_migration(FILENAME)

        with _patched(
            migration,
            tables={"inventory_levels"},
            unique_constraints={
                "inventory_levels": ["inventory_levels_product_id_key"]
            },
        ) as mock_op:
            migration.downgrade()

        mock_op.drop_index.assert_not_called()
        mock_op.create_unique_constraint.assert_not_called()
