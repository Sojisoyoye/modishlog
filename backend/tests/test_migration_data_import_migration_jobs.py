"""Content tests for migration bc0d9bce053d, hardened for idempotency
after a real local dev database was found stuck at an old alembic_version
(ad6011a90709) while its actual schema already had migration_jobs plus
every table's migration_id column/FK/index — the exact same class of
untracked-drift bug as aaf1881e3f19 and the 4 migrations hardened in
test_migration_variant_and_consumption_idempotency.py, just discovered
locally instead of on staging/prod.

See test_migration_image_url_mix_target_business_id.py for why a
live-DB round-trip test isn't feasible here (CI never runs `alembic
upgrade head` against a real database before pytest).
"""

from tests.migration_test_utils import load_migration
from tests.migration_test_utils import patched_migration_utils as _patched

FILENAME = "bc0d9bce053d_add_data_import_migration_jobs.py"


def _all_tables_fully_migrated_kwargs(migration):
    """Build mock_inspector() kwargs describing every MIGRATION_ID_TABLES
    entry as already having its migration_id column/FK/index — the exact
    state this migration's upgrade() must recognize as fully done."""
    tables = {"migration_jobs", *migration.MIGRATION_ID_TABLES}
    columns = {t: ["migration_id"] for t in migration.MIGRATION_ID_TABLES}
    foreign_keys = {t: [f"fk_{t}_migration_id"] for t in migration.MIGRATION_ID_TABLES}
    indexes = {"migration_jobs": ["ix_migration_jobs_business_id"]}
    indexes.update({t: [f"ix_{t}_migration_id"] for t in migration.MIGRATION_ID_TABLES})
    return {
        "tables": tables,
        "columns": columns,
        "foreign_keys": foreign_keys,
        "indexes": indexes,
    }


class TestDataImportMigrationJobsMigrationUpgrade:
    def test_fresh_db_adds_everything(self):
        migration = load_migration(FILENAME)

        with _patched(migration) as mock_op:
            migration.upgrade()

        mock_op.create_table.assert_called_once()
        add_column_tables = [c.args[0] for c in mock_op.add_column.call_args_list]
        assert add_column_tables == migration.MIGRATION_ID_TABLES
        assert mock_op.create_foreign_key.call_count == len(
            migration.MIGRATION_ID_TABLES
        )
        # +1 for migration_jobs' own ix_migration_jobs_business_id index
        assert mock_op.create_index.call_count == len(migration.MIGRATION_ID_TABLES) + 1

    def test_full_noop_when_everything_already_exists(self):
        """The exact drift scenario this migration hit: migration_jobs and
        every table's migration_id column/FK/index already exist (created
        outside Alembic tracking), but alembic_version was still behind —
        must add nothing."""
        migration = load_migration(FILENAME)

        with _patched(
            migration, **_all_tables_fully_migrated_kwargs(migration)
        ) as mock_op:
            migration.upgrade()

        mock_op.create_table.assert_not_called()
        mock_op.add_column.assert_not_called()
        mock_op.create_foreign_key.assert_not_called()
        mock_op.create_index.assert_not_called()

    def test_upgrade_adds_only_the_missing_pieces_for_one_drifted_table(self):
        """A partial-drift variant: migration_jobs and every table's
        migration_id column/FK/index exist except one table (the last in
        MIGRATION_ID_TABLES) which is missing everything — must add only
        that table's column/FK/index, not touch the other 22."""
        migration = load_migration(FILENAME)
        drifted_table = migration.MIGRATION_ID_TABLES[-1]
        kwargs = _all_tables_fully_migrated_kwargs(migration)
        kwargs["columns"] = {
            t: cols for t, cols in kwargs["columns"].items() if t != drifted_table
        }
        kwargs["foreign_keys"] = {
            t: fks for t, fks in kwargs["foreign_keys"].items() if t != drifted_table
        }
        kwargs["indexes"] = {
            t: idxs for t, idxs in kwargs["indexes"].items() if t != f"{drifted_table}"
        }
        kwargs["indexes"].pop(drifted_table, None)

        with _patched(migration, **kwargs) as mock_op:
            migration.upgrade()

        mock_op.create_table.assert_not_called()
        add_column_tables = [c.args[0] for c in mock_op.add_column.call_args_list]
        assert add_column_tables == [drifted_table]
        fk_tables = [c.args[1] for c in mock_op.create_foreign_key.call_args_list]
        assert fk_tables == [drifted_table]
        index_tables = [c.args[1] for c in mock_op.create_index.call_args_list]
        assert index_tables == [drifted_table]


class TestDataImportMigrationJobsMigrationDowngrade:
    def test_full_noop_when_nothing_exists(self):
        migration = load_migration(FILENAME)

        with _patched(migration) as mock_op:
            migration.downgrade()  # must not raise

        mock_op.drop_index.assert_not_called()
        mock_op.drop_constraint.assert_not_called()
        mock_op.drop_column.assert_not_called()
        mock_op.drop_table.assert_not_called()

    def test_fresh_then_downgrade_drops_everything(self):
        migration = load_migration(FILENAME)

        with _patched(
            migration, **_all_tables_fully_migrated_kwargs(migration)
        ) as mock_op:
            migration.downgrade()

        assert mock_op.drop_index.call_count == len(migration.MIGRATION_ID_TABLES) + 1
        assert mock_op.drop_constraint.call_count == len(migration.MIGRATION_ID_TABLES)
        drop_column_tables = [c.args[0] for c in mock_op.drop_column.call_args_list]
        assert drop_column_tables == list(reversed(migration.MIGRATION_ID_TABLES))
        mock_op.drop_table.assert_called_once_with("migration_jobs")


class TestDataImportMigrationJobsMigrationMeta:
    def test_revision_chain_unchanged(self):
        migration = load_migration(FILENAME)

        assert migration.revision == "bc0d9bce053d"
        assert migration.down_revision == "f1e2d3c4b5a6"
