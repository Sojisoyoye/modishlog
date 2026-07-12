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

from tests.migration_test_utils import load_migration
from tests.migration_test_utils import patched_migration_utils as _patched

MIGRATION_FILENAME = "aaf1881e3f19_add_missing_image_url_and_mix_target_business_id.py"


def _load_migration():
    return load_migration(MIGRATION_FILENAME)


class TestImageUrlMixTargetBusinessIdMigrationUpgrade:
    def test_fresh_db_adds_everything(self):
        """Original behaviour, preserved: nothing exists yet, so every
        column/FK/index/constraint gets created, and business_id is
        backfilled + made NOT NULL."""
        migration = _load_migration()

        with _patched(migration) as mock_op:
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

        with _patched(
            migration,
            tables={"products", "product_mix_targets"},
            columns={"products": {"image_url": {"nullable": True}}},
        ) as mock_op:
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

        with _patched(
            migration,
            tables={"products", "product_mix_targets"},
            columns={
                "products": {"image_url": {"nullable": True}},
                "product_mix_targets": {"business_id": {"nullable": True}},
            },
        ) as mock_op:
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

        with _patched(
            migration,
            tables={"products", "product_mix_targets"},
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
        ) as mock_op:
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

        with _patched(
            migration,
            tables={"products", "product_mix_targets"},
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
        ) as mock_op:
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

        with _patched(
            migration,
            tables={"products", "product_mix_targets"},
            columns={"products": {"image_url": {"nullable": True}}},
            # product_mix_targets.business_id and its FK/index/constraint
            # were never added — e.g. upgrade() no-op'd on a DB where
            # they didn't exist and business_id ended up populated by
            # some other means outside this migration's control.
        ) as mock_op:
            migration.downgrade()  # must not raise

        mock_op.drop_constraint.assert_not_called()
        mock_op.drop_index.assert_not_called()
        drop_column_tables = [c.args[0] for c in mock_op.drop_column.call_args_list]
        assert drop_column_tables == ["products"]

    def test_full_noop_when_nothing_exists(self):
        migration = _load_migration()

        with _patched(migration) as mock_op:
            migration.downgrade()  # must not raise

        mock_op.drop_constraint.assert_not_called()
        mock_op.drop_index.assert_not_called()
        mock_op.drop_column.assert_not_called()


class TestImageUrlMixTargetBusinessIdMigrationMeta:
    def test_revision_chain_unchanged(self):
        migration = _load_migration()

        assert migration.revision == "aaf1881e3f19"
        assert migration.down_revision == "5b084b6ad359"
