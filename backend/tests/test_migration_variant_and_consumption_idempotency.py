"""Content tests for the 4 task-165/166/170/171 migrations hardened for
idempotency after 00db7d1e1a78 hit real staging schema drift (staging's
actual schema had inventory_batches.variant_id already, outside Alembic
tracking, blocking every migration behind it — same class of bug as
migration aaf1881e3f19, which hit the identical failure mode first).

See test_migration_image_url_mix_target_business_id.py for why a
live-DB round-trip test isn't feasible here (CI never runs `alembic
upgrade head` against a real database before pytest).
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from src.core import migration_utils
from tests.migration_test_utils import load_migration, mock_inspector


@contextmanager
def _patched(migration, **inspector_kwargs):
    """Patch the migration's own `op` (captures/no-ops its direct DDL
    calls) and migration_utils' `op` + `sa.inspect` (controls what the
    shared has_column/has_table/etc. helpers see) at once."""
    with patch.object(migration, "op") as mock_op, patch.object(
        migration_utils, "op", MagicMock()
    ), patch.object(
        migration_utils.sa, "inspect", return_value=mock_inspector(**inspector_kwargs)
    ):
        yield mock_op


class TestInventoryBatchesVariantIdMigration:
    FILENAME = "00db7d1e1a78_add_variant_id_to_inventory_batches.py"

    def test_fresh_db_adds_everything(self):
        migration = load_migration(self.FILENAME)

        with _patched(migration) as mock_op:
            migration.upgrade()

        mock_op.add_column.assert_called_once()
        mock_op.create_foreign_key.assert_called_once()
        mock_op.create_index.assert_called_once()

    def test_full_noop_when_everything_already_exists(self):
        migration = load_migration(self.FILENAME)

        with _patched(
            migration,
            tables={"inventory_batches"},
            columns={"inventory_batches": ["variant_id"]},
            foreign_keys={"inventory_batches": ["fk_inventory_batches_variant_id"]},
            indexes={"inventory_batches": ["ix_inventory_batches_variant_id"]},
        ) as mock_op:
            migration.upgrade()

        mock_op.add_column.assert_not_called()
        mock_op.create_foreign_key.assert_not_called()
        mock_op.create_index.assert_not_called()

    def test_downgrade_noop_when_nothing_exists(self):
        migration = load_migration(self.FILENAME)

        with _patched(migration) as mock_op:
            migration.downgrade()  # must not raise

        mock_op.drop_index.assert_not_called()
        mock_op.drop_constraint.assert_not_called()
        mock_op.drop_column.assert_not_called()


class TestFifoConsumptionsTableMigration:
    FILENAME = "9100b1b36d72_add_fifo_consumptions_table.py"

    def test_fresh_db_adds_everything(self):
        migration = load_migration(self.FILENAME)

        with _patched(migration) as mock_op:
            migration.upgrade()

        mock_op.create_table.assert_called_once()
        assert mock_op.create_index.call_count == 2

    def test_full_noop_when_everything_already_exists(self):
        migration = load_migration(self.FILENAME)

        with _patched(
            migration,
            tables={"fifo_consumptions"},
            indexes={
                "fifo_consumptions": [
                    "ix_fifo_consumptions_sale_id",
                    "ix_fifo_consumptions_batch_id",
                ]
            },
        ) as mock_op:
            migration.upgrade()

        mock_op.create_table.assert_not_called()
        mock_op.create_index.assert_not_called()

    def test_downgrade_noop_when_table_missing(self):
        migration = load_migration(self.FILENAME)

        with _patched(migration) as mock_op:
            migration.downgrade()  # must not raise

        mock_op.drop_table.assert_not_called()
        mock_op.drop_index.assert_not_called()

    def test_downgrade_skips_an_already_missing_index(self):
        """The table exists but ix_fifo_consumptions_batch_id was already
        dropped by some prior partial operation — downgrade() must not
        hard-fail trying to drop a nonexistent index (the exact class of
        drift bug this PR fixes elsewhere)."""
        migration = load_migration(self.FILENAME)

        with _patched(
            migration,
            tables={"fifo_consumptions"},
            indexes={"fifo_consumptions": ["ix_fifo_consumptions_sale_id"]},
        ) as mock_op:
            migration.downgrade()  # must not raise

        dropped_indexes = [c.args[0] for c in mock_op.drop_index.call_args_list]
        assert dropped_indexes == ["ix_fifo_consumptions_sale_id"]
        mock_op.drop_table.assert_called_once()


class TestLotConsumptionsTableMigration:
    FILENAME = "fdb77f054f7e_add_lot_consumptions_table.py"

    def test_fresh_db_adds_everything(self):
        migration = load_migration(self.FILENAME)

        with _patched(migration) as mock_op:
            migration.upgrade()

        mock_op.create_table.assert_called_once()
        assert mock_op.create_index.call_count == 2

    def test_full_noop_when_everything_already_exists(self):
        migration = load_migration(self.FILENAME)

        with _patched(
            migration,
            tables={"lot_consumptions"},
            indexes={
                "lot_consumptions": [
                    "ix_lot_consumptions_sale_id",
                    "ix_lot_consumptions_order_line_item_id",
                ]
            },
        ) as mock_op:
            migration.upgrade()

        mock_op.create_table.assert_not_called()
        mock_op.create_index.assert_not_called()

    def test_downgrade_noop_when_table_missing(self):
        migration = load_migration(self.FILENAME)

        with _patched(migration) as mock_op:
            migration.downgrade()  # must not raise

        mock_op.drop_table.assert_not_called()
        mock_op.drop_index.assert_not_called()

    def test_downgrade_skips_an_already_missing_index(self):
        """The table exists but ix_lot_consumptions_order_line_item_id was
        already dropped by some prior partial operation — downgrade()
        must not hard-fail trying to drop a nonexistent index."""
        migration = load_migration(self.FILENAME)

        with _patched(
            migration,
            tables={"lot_consumptions"},
            indexes={"lot_consumptions": ["ix_lot_consumptions_sale_id"]},
        ) as mock_op:
            migration.downgrade()  # must not raise

        dropped_indexes = [c.args[0] for c in mock_op.drop_index.call_args_list]
        assert dropped_indexes == ["ix_lot_consumptions_sale_id"]
        mock_op.drop_table.assert_called_once()


class TestPriceSuggestionsVariantIdMigration:
    FILENAME = "78362e79f979_add_variant_id_to_price_suggestions.py"

    def test_fresh_db_adds_everything(self):
        migration = load_migration(self.FILENAME)

        with _patched(migration) as mock_op:
            migration.upgrade()

        mock_op.add_column.assert_called_once()
        mock_op.create_foreign_key.assert_called_once()
        mock_op.create_index.assert_called_once()

    def test_full_noop_when_everything_already_exists(self):
        migration = load_migration(self.FILENAME)

        with _patched(
            migration,
            tables={"price_suggestions"},
            columns={"price_suggestions": ["variant_id"]},
            foreign_keys={"price_suggestions": ["fk_price_suggestions_variant_id"]},
            indexes={"price_suggestions": ["ix_price_suggestions_variant_id"]},
        ) as mock_op:
            migration.upgrade()

        mock_op.add_column.assert_not_called()
        mock_op.create_foreign_key.assert_not_called()
        mock_op.create_index.assert_not_called()

    def test_downgrade_noop_when_nothing_exists(self):
        migration = load_migration(self.FILENAME)

        with _patched(migration) as mock_op:
            migration.downgrade()  # must not raise

        mock_op.drop_index.assert_not_called()
        mock_op.drop_constraint.assert_not_called()
        mock_op.drop_column.assert_not_called()
