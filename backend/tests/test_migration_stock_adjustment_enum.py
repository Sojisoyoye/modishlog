"""Content test for migration 7a29c684a562 (task 167).

The rest of the test suite mocks db.execute entirely, so nothing catches
this migration's actual SQL being edited or reverted incorrectly later —
CI provisions a fresh Postgres service for pytest but never runs `alembic
upgrade head` against it first, so a live-DB round-trip test isn't
feasible here without also changing CI. This instead asserts on the
migration module's own upgrade() behavior: that it emits exactly the two
ALTER TYPE statements adding the upper-case labels the movementtype enum
was missing, confirmed manually (see PR #309) against real historical
data to be the correct, minimal fix.
"""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

MIGRATION_PATH = (
    Path(__file__).parent.parent
    / "alembic"
    / "versions"
    / "7a29c684a562_add_uppercase_stock_adjustment_opening_stock.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_7a29c684a562", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestStockAdjustmentEnumMigration:
    def test_upgrade_adds_both_uppercase_labels(self):
        migration = _load_migration()

        with patch.object(migration, "op") as mock_op:
            migration.upgrade()

        executed_sql = [call.args[0] for call in mock_op.execute.call_args_list]
        assert executed_sql == [
            "ALTER TYPE movementtype ADD VALUE IF NOT EXISTS 'STOCK_ADJUSTMENT'",
            "ALTER TYPE movementtype ADD VALUE IF NOT EXISTS 'OPENING_STOCK'",
        ]

    def test_upgrade_never_touches_the_six_existing_labels(self):
        """The fix must be purely additive — no ALTER TYPE RENAME, no
        data-rewriting UPDATE against stock_movements, nothing that could
        touch the 6 labels (and every existing row) already in use."""
        migration = _load_migration()

        with patch.object(migration, "op") as mock_op:
            migration.upgrade()

        for call in mock_op.execute.call_args_list:
            sql = call.args[0]
            assert "UPDATE" not in sql.upper()
            assert "RENAME" not in sql.upper()
            assert "DROP" not in sql.upper()

    def test_downgrade_does_not_error(self):
        """Postgres has no ALTER TYPE ... DROP VALUE — downgrade is an
        intentional no-op (see migration docstring), not an oversight."""
        migration = _load_migration()

        with patch.object(migration, "op", MagicMock()):
            migration.downgrade()  # must not raise

    def test_revision_chain_links_to_the_fifo_consumptions_migration(self):
        migration = _load_migration()

        assert migration.down_revision == "9100b1b36d72"
