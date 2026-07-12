"""Content test for migration aaf1881e3f19.

CI provisions a fresh Postgres service for pytest but never runs `alembic
upgrade head` against it first, so a live-DB round-trip test isn't
feasible here without also changing CI (same constraint as
test_migration_stock_adjustment_enum.py, task 167). This instead asserts
on the migration module's own upgrade()/downgrade() behavior directly.

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


def _mock_inspector(columns=None, foreign_keys=None, unique_constraints=None, indexes=None):
    """Stand-in for sa.inspect(op.get_bind()).

    columns: table -> {column_name: {"nullable": bool}} — a column absent
    from this dict simply doesn't exist yet.
    foreign_keys / unique_constraints / indexes: table -> list of names
    already present. Routed to their real Postgres-reporting methods
    separately (get_foreign_keys vs get_unique_constraints) so a bug in
    either code path is actually exercised, not silently masked by an
    OR-together check that only ever gets fed one of the two.
    """
    columns = columns or {}
    foreign_keys = foreign_keys or {}
    unique_constraints = unique_constraints or {}
    indexes = indexes or {}
    inspector = MagicMock()
    inspector.get_columns.side_effect = lambda table: [
        {"name": name, "nullable": info["nullable"]}
        for name, info in columns.get(table, {}).items()
    ]
    inspector.get_foreign_keys.side_effect = lambda table: [
        {"name": n} for n in foreign_keys.get(table, [])
    ]
    inspector.get_unique_constraints.side_effect = lambda table: [
        {"name": n} for n in unique_constraints.get(table, [])
    ]
    inspector.get_indexes.side_effect = lambda table: [
        {"name": n} for n in indexes.get(table, [])
    ]
    return inspector


class TestImageUrlMixTargetBusinessIdMigrationUpgrade:
    def test_fresh_db_adds_everything(self):
        """Original behaviour, preserved: nothing exists yet, so every
        column/FK/index/constraint gets created, and business_id is
        backfilled + made NOT NULL."""
        migration = _load_migration()

        with patch.object(migration, "op") as mock_op, patch.object(
            migration.sa, "inspect", return_value=_mock_inspector()
        ):
            migration.upgrade()

        add_column_tables = [c.args[0] for c in mock_op.add_column.call_args_list]
        assert add_column_tables == ["products", "product_mix_targets"]
        mock_op.execute.assert_called_once()
        mock_op.alter_column.assert_called_once_with(
            "product_mix_targets", "business_id", nullable=False
        )
        mock_op.create_foreign_key.assert_called_once()
        mock_op.create_index.assert_called_once()
        mock_op.create_unique_constraint.assert_called_once()

    def test_skips_image_url_when_already_backfilled(self):
        """The exact staging/prod drift scenario: products.image_url was
        added via emergency raw SQL before this migration ever ran, but
        product_mix_targets.business_id was not touched by that patch."""
        migration = _load_migration()
        inspector = _mock_inspector(
            columns={"products": {"image_url": {"nullable": True}}}
        )

        with patch.object(migration, "op") as mock_op, patch.object(
            migration.sa, "inspect", return_value=inspector
        ):
            migration.upgrade()

        add_column_tables = [c.args[0] for c in mock_op.add_column.call_args_list]
        assert add_column_tables == ["product_mix_targets"]
        mock_op.execute.assert_called_once()
        mock_op.alter_column.assert_called_once()
        mock_op.create_foreign_key.assert_called_once()
        mock_op.create_index.assert_called_once()
        mock_op.create_unique_constraint.assert_called_once()

    def test_backfills_when_column_exists_but_still_nullable(self):
        """If business_id was added by some other means (a partial manual
        fix, or a prior migration attempt that failed partway through)
        but was never backfilled or made NOT NULL, the migration must
        still run the backfill + NOT NULL enforcement — column existence
        alone must not be treated as 'already finalized', or rows are
        left with a NULL business_id that the ORM model and application
        code assume is always populated."""
        migration = _load_migration()
        inspector = _mock_inspector(
            columns={
                "products": {"image_url": {"nullable": True}},
                "product_mix_targets": {"business_id": {"nullable": True}},
            }
        )

        with patch.object(migration, "op") as mock_op, patch.object(
            migration.sa, "inspect", return_value=inspector
        ):
            migration.upgrade()

        # Column already exists — must not try to add it again.
        add_column_tables = [c.args[0] for c in mock_op.add_column.call_args_list]
        assert "product_mix_targets" not in add_column_tables
        # But it's still nullable — backfill and NOT NULL enforcement must run.
        mock_op.execute.assert_called_once()
        mock_op.alter_column.assert_called_once_with(
            "product_mix_targets", "business_id", nullable=False
        )

    def test_full_noop_when_everything_already_exists(self):
        """Re-running against an already-fully-migrated DB (the normal
        idempotent-migration case) must not attempt to add, backfill, or
        constrain anything a second time."""
        migration = _load_migration()
        inspector = _mock_inspector(
            columns={
                "products": {"image_url": {"nullable": True}},
                "product_mix_targets": {"business_id": {"nullable": False}},
            },
            foreign_keys={
                "product_mix_targets": ["fk_product_mix_targets_business_id"]
            },
            unique_constraints={
                "product_mix_targets": ["uq_mix_target_category_business"]
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


class TestImageUrlMixTargetBusinessIdMigrationDowngrade:
    def test_fresh_db_upgrade_then_downgrade_drops_everything(self):
        """The normal case: everything this migration created still
        exists, so downgrade() removes all of it."""
        migration = _load_migration()
        inspector = _mock_inspector(
            columns={
                "products": {"image_url": {"nullable": True}},
                "product_mix_targets": {"business_id": {"nullable": False}},
            },
            foreign_keys={
                "product_mix_targets": ["fk_product_mix_targets_business_id"]
            },
            unique_constraints={
                "product_mix_targets": ["uq_mix_target_category_business"]
            },
            indexes={"product_mix_targets": ["ix_product_mix_targets_business_id"]},
        )

        with patch.object(migration, "op") as mock_op, patch.object(
            migration.sa, "inspect", return_value=inspector
        ):
            migration.downgrade()

        mock_op.drop_constraint.assert_any_call(
            "uq_mix_target_category_business", "product_mix_targets", type_="unique"
        )
        mock_op.drop_constraint.assert_any_call(
            "fk_product_mix_targets_business_id",
            "product_mix_targets",
            type_="foreignkey",
        )
        mock_op.drop_index.assert_called_once_with(
            "ix_product_mix_targets_business_id", table_name="product_mix_targets"
        )
        drop_column_calls = [
            (c.args[0], c.args[1]) for c in mock_op.drop_column.call_args_list
        ]
        assert ("product_mix_targets", "business_id") in drop_column_calls
        assert ("products", "image_url") in drop_column_calls

    def test_partial_state_downgrade_only_drops_what_exists(self):
        """downgrade() must not raise (e.g. UndefinedColumn) when run
        against a partially-applied state — e.g. upgrade() was run
        against an already-drifted DB (this PR's whole point) where some
        of what a naive downgrade would try to drop was never actually
        created by *this* migration in the first place."""
        migration = _load_migration()
        inspector = _mock_inspector(
            columns={"products": {"image_url": {"nullable": True}}}
            # product_mix_targets.business_id and its FK/index/constraint
            # were never added — e.g. upgrade() no-op'd on a DB where
            # they didn't exist and business_id ended up populated by
            # some other means outside this migration's control.
        )

        with patch.object(migration, "op") as mock_op, patch.object(
            migration.sa, "inspect", return_value=inspector
        ):
            migration.downgrade()  # must not raise

        mock_op.drop_constraint.assert_not_called()
        mock_op.drop_index.assert_not_called()
        drop_column_tables = [c.args[0] for c in mock_op.drop_column.call_args_list]
        assert drop_column_tables == ["products"]

    def test_full_noop_when_nothing_exists(self):
        migration = _load_migration()
        inspector = _mock_inspector()

        with patch.object(migration, "op") as mock_op, patch.object(
            migration.sa, "inspect", return_value=inspector
        ):
            migration.downgrade()  # must not raise

        mock_op.drop_constraint.assert_not_called()
        mock_op.drop_index.assert_not_called()
        mock_op.drop_column.assert_not_called()


class TestImageUrlMixTargetBusinessIdMigrationMeta:
    def test_revision_chain_unchanged(self):
        migration = _load_migration()

        assert migration.revision == "aaf1881e3f19"
        assert migration.down_revision == "5b084b6ad359"
