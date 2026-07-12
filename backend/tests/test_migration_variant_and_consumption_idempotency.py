"""Content tests for the 4 task-165/166/170/171 migrations hardened for
idempotency after 00db7d1e1a78 hit real staging schema drift (staging's
actual schema had inventory_batches.variant_id already, outside Alembic
tracking, blocking every migration behind it — same class of bug as
migration aaf1881e3f19, which hit the identical failure mode first).

See test_migration_image_url_mix_target_business_id.py for why a
live-DB round-trip test isn't feasible here (CI never runs `alembic
upgrade head` against a real database before pytest).
"""

from tests.migration_test_utils import load_migration
from tests.migration_test_utils import patched_migration_utils as _patched


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

    def test_upgrade_adds_only_the_missing_fk_when_column_already_exists(self):
        """The exact staging drift scenario this PR targets: variant_id
        already exists (outside Alembic tracking) but its FK/index were
        never created — must add only what's missing, not re-add the
        column or skip the still-missing FK/index."""
        migration = load_migration(self.FILENAME)

        with _patched(
            migration,
            tables={"inventory_batches"},
            columns={"inventory_batches": ["variant_id"]},
        ) as mock_op:
            migration.upgrade()

        mock_op.add_column.assert_not_called()
        mock_op.create_foreign_key.assert_called_once()
        mock_op.create_index.assert_called_once()

    def test_upgrade_adds_only_the_missing_index_when_fk_already_exists(self):
        migration = load_migration(self.FILENAME)

        with _patched(
            migration,
            tables={"inventory_batches"},
            columns={"inventory_batches": ["variant_id"]},
            foreign_keys={"inventory_batches": ["fk_inventory_batches_variant_id"]},
        ) as mock_op:
            migration.upgrade()

        mock_op.add_column.assert_not_called()
        mock_op.create_foreign_key.assert_not_called()
        mock_op.create_index.assert_called_once()


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

    def test_upgrade_adds_only_the_missing_index_when_table_already_exists(self):
        """The exact staging drift scenario this PR targets: the table
        exists (outside Alembic tracking) but one index was never
        created — must not re-create the table, and must add only the
        genuinely missing index."""
        migration = load_migration(self.FILENAME)

        with _patched(
            migration,
            tables={"fifo_consumptions"},
            indexes={"fifo_consumptions": ["ix_fifo_consumptions_sale_id"]},
        ) as mock_op:
            migration.upgrade()

        mock_op.create_table.assert_not_called()
        mock_op.create_index.assert_called_once_with(
            "ix_fifo_consumptions_batch_id", "fifo_consumptions", ["batch_id"]
        )

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

    def test_upgrade_adds_only_the_missing_index_when_table_already_exists(self):
        """The exact staging drift scenario this PR targets: the table
        exists (outside Alembic tracking) but one index was never
        created — must not re-create the table, and must add only the
        genuinely missing index."""
        migration = load_migration(self.FILENAME)

        with _patched(
            migration,
            tables={"lot_consumptions"},
            indexes={"lot_consumptions": ["ix_lot_consumptions_sale_id"]},
        ) as mock_op:
            migration.upgrade()

        mock_op.create_table.assert_not_called()
        mock_op.create_index.assert_called_once_with(
            "ix_lot_consumptions_order_line_item_id",
            "lot_consumptions",
            ["order_line_item_id"],
        )

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

    def test_upgrade_adds_only_the_missing_fk_when_column_already_exists(self):
        """The exact staging drift scenario this PR targets: variant_id
        already exists (outside Alembic tracking) but its FK/index were
        never created — must add only what's missing, not re-add the
        column or skip the still-missing FK/index."""
        migration = load_migration(self.FILENAME)

        with _patched(
            migration,
            tables={"price_suggestions"},
            columns={"price_suggestions": ["variant_id"]},
        ) as mock_op:
            migration.upgrade()

        mock_op.add_column.assert_not_called()
        mock_op.create_foreign_key.assert_called_once()
        mock_op.create_index.assert_called_once()

    def test_upgrade_adds_only_the_missing_index_when_fk_already_exists(self):
        migration = load_migration(self.FILENAME)

        with _patched(
            migration,
            tables={"price_suggestions"},
            columns={"price_suggestions": ["variant_id"]},
            foreign_keys={"price_suggestions": ["fk_price_suggestions_variant_id"]},
        ) as mock_op:
            migration.upgrade()

        mock_op.add_column.assert_not_called()
        mock_op.create_foreign_key.assert_not_called()
        mock_op.create_index.assert_called_once()

    def test_downgrade_noop_when_nothing_exists(self):
        migration = load_migration(self.FILENAME)

        with _patched(migration) as mock_op:
            migration.downgrade()  # must not raise

        mock_op.drop_index.assert_not_called()
        mock_op.drop_constraint.assert_not_called()
        mock_op.drop_column.assert_not_called()
