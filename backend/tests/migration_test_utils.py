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
from pathlib import Path
from types import ModuleType

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
