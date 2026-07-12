"""Shared helper for migration content tests.

CI provisions a fresh Postgres service for pytest but never runs `alembic
upgrade head` against it first, so a live-DB round-trip test isn't
feasible for individual migrations (see task 167's
test_migration_stock_adjustment_enum.py, task 170/171's
test_migration_image_url_mix_target_business_id.py). Migration content
tests instead load the migration module directly and assert on its own
upgrade()/downgrade() behavior via mocked op/sa.inspect.
"""

import importlib.util
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

VERSIONS_DIR = Path(__file__).parent.parent / "alembic" / "versions"


def load_migration(filename: str) -> ModuleType:
    """Load an Alembic migration file as a standalone module by filename
    (e.g. "aaf1881e3f19_add_missing_image_url_and_mix_target_business_id.py"),
    so its upgrade()/downgrade() can be called directly and its op/sa
    references patched."""
    path = VERSIONS_DIR / filename
    spec = importlib.util.spec_from_file_location(f"migration_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mock_inspector(
    tables=(), columns=None, foreign_keys=None, unique_constraints=None, indexes=None
):
    """Stand-in for sa.inspect(op.get_bind()), shared across migration
    content tests.

    tables: set/collection of table names that "exist" (has_table()).
    columns: table -> either a list of column names, or a dict of
        {column_name: {"nullable": bool}} when a test cares about
        nullability (e.g. a column that exists but was never finalized).
        The plain-list form defaults every column to nullable=True.
    foreign_keys / unique_constraints / indexes: table -> list of names
        already present, routed to their real, separate Postgres-
        reporting methods (get_foreign_keys vs get_unique_constraints)
        so a bug in either code path is actually exercised.
    """
    columns = columns or {}
    foreign_keys = foreign_keys or {}
    unique_constraints = unique_constraints or {}
    indexes = indexes or {}

    def _columns_for(table):
        table_columns = columns.get(table, {})
        if not isinstance(table_columns, dict):
            table_columns = {name: {"nullable": True} for name in table_columns}
        return [
            {"name": name, "nullable": info.get("nullable", True)}
            for name, info in table_columns.items()
        ]

    inspector = MagicMock()
    inspector.has_table.side_effect = lambda table: table in tables
    inspector.get_columns.side_effect = _columns_for
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


@contextmanager
def patched_migration_utils(migration=None, **inspector_kwargs):
    """Patch src.core.migration_utils' `op` (so op.get_bind() doesn't hit
    the real Alembic proxy, which raises outside an active migration
    context) and `sa.inspect` (to return a fixed mock_inspector(**kwargs)
    regardless of what op.get_bind() returns) — shared across
    test_migration_utils.py (tests migration_utils' functions directly)
    and every migration content test (tests a migration module's own
    upgrade()/downgrade(), which call into migration_utils).

    If `migration` is given, also patches *its own* `op` (capturing/
    no-op'ing its direct DDL calls like add_column/create_table) and
    yields that mock; otherwise yields None.
    """
    from src.core import migration_utils

    with ExitStack() as stack:
        mock_op = None
        if migration is not None:
            mock_op = stack.enter_context(patch.object(migration, "op"))
        stack.enter_context(patch.object(migration_utils, "op", MagicMock()))
        stack.enter_context(
            patch.object(
                migration_utils.sa,
                "inspect",
                return_value=mock_inspector(**inspector_kwargs),
            )
        )
        yield mock_op
