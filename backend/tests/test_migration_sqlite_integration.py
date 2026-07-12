"""Real-engine (SQLite in-memory) integration tests for the two
table-creating migrations hardened in this PR.

Unlike the rest of this codebase's migration content tests (mocked
op/sa.inspect — see migration_test_utils.py's docstring for why a
Postgres round-trip isn't feasible here), these run upgrade()/downgrade()
against a genuinely real Inspector with real (non-mocked) reflection
semantics — a static mock_inspector side_effect function can't model
SQLAlchemy's Inspector reflection-result caching per-instance (confirmed
directly against a live connection: querying has_table() before a table
is created, then creating it, then re-querying the *same* Inspector
object returns the stale pre-creation answer — see
src/core/migration_utils.py's docstring for the full writeup and why
9100b1b36d72/fdb77f054f7e's upgrade() rebuilds `insp` after
create_table()).

For these two migrations' specific check order, tracing it through shows
that staleness doesn't currently cause an observably wrong outcome (the
stale "index doesn't exist" answer happens to match the true state right
after the table's own creation, and each upgrade()/downgrade() call
builds its own fresh top-level Inspector, so there's no cross-call
leakage either) — the `insp` rebuild is defensive hardening against a
future edit changing that check order, not a fix for an active bug here.
These tests exist as real, non-mocked correctness coverage (create,
re-run idempotently, downgrade) rather than as a regression guard for
that specific latent hazard.

An in-memory SQLite engine is not a "live DB" in the production sense —
no external service, no Docker, no CI change, sub-millisecond — just a
real Inspector with real reflection semantics.
"""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

VERSIONS_DIR = Path(__file__).parent.parent / "alembic" / "versions"


def _load_migration(filename: str):
    path = VERSIONS_DIR / filename
    spec = importlib.util.spec_from_file_location(f"sqlite_it_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "filename,table,index_names",
    [
        (
            "9100b1b36d72_add_fifo_consumptions_table.py",
            "fifo_consumptions",
            {"ix_fifo_consumptions_sale_id", "ix_fifo_consumptions_batch_id"},
        ),
        (
            "fdb77f054f7e_add_lot_consumptions_table.py",
            "lot_consumptions",
            {
                "ix_lot_consumptions_sale_id",
                "ix_lot_consumptions_order_line_item_id",
            },
        ),
    ],
)
class TestTableCreatingMigrationsAgainstRealEngine:
    def test_upgrade_creates_table_and_both_indexes(self, filename, table, index_names):
        migration = _load_migration(filename)
        engine = sa.create_engine("sqlite:///:memory:")

        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                from alembic import op

                migration.upgrade()

                insp = sa.inspect(op.get_bind())
                assert insp.has_table(table) is True
                assert {i["name"] for i in insp.get_indexes(table)} == index_names

    def test_upgrade_rerun_is_a_clean_noop(self, filename, table, index_names):
        """The exact regression this test suite exists to catch: if
        upgrade() reused a stale (pre-create_table) Inspector for the
        has_index() checks, a second upgrade() run against the
        now-existing table+indexes would try to create_index() again and
        raise (SQLite: "index ... already exists")."""
        migration = _load_migration(filename)
        engine = sa.create_engine("sqlite:///:memory:")

        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()
                migration.upgrade()  # must not raise

    def test_downgrade_removes_everything(self, filename, table, index_names):
        migration = _load_migration(filename)
        engine = sa.create_engine("sqlite:///:memory:")

        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                from alembic import op

                migration.upgrade()
                migration.downgrade()

                insp = sa.inspect(op.get_bind())
                assert insp.has_table(table) is False
