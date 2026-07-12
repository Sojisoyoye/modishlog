"""Shared idempotency helpers for Alembic migrations.

Lives under src/ (not backend/alembic/) because alembic's own package
name would collide with a local `backend/alembic/migration_utils.py` —
migration files already do `from alembic import op` against the
installed package, and `env.py` already imports freely from `src.*`
(the app root is on the path when Alembic runs), so this is the safe
place for migration-only helpers to live.

CI never runs `alembic upgrade head` against a real database before
pytest (it provisions a fresh schema instead — see backend/tests/
migration_test_utils.py), so a migration's first real exercise is often
a live deploy — by which point staging/prod may have already drifted
from what alembic_version claims (a schema change applied outside
Alembic tracking, an earlier migration attempt that committed this
table/column before failing on a later step, etc — see migration
aaf1881e3f19 and task 165-171's migrations, all of which hit exactly
this in production/staging deploys).

These helpers let a migration check "does this already exist?" before
issuing DDL, so `alembic upgrade head` self-heals against that drift
instead of hard failing with e.g. DuplicateColumnError/DuplicateTable
and permanently blocking every migration after it.

Each function accepts an optional pre-built `insp`. A migration checking
several things in one upgrade()/downgrade() call should build one
Inspector via `sa.inspect(op.get_bind())` and pass it to every has_*
call, rather than letting each call construct its own — this only saves
the Inspector *construction* cost, not the live has_table() re-query
each has_* call still performs, since SQLAlchemy's Inspector does not
cache plain `insp.has_table()`/`insp.get_*()` calls made without an
explicit info_cache.

CAUTION — the one place this reuse is NOT safe: SQLAlchemy's Inspector
*does* cache reflection results per-instance once it has answered a
given (table, reflection-type) question once (confirmed against a live
connection: `insp.has_table('t')` returns False, the table is then
created on the same connection, and the *same* `insp.has_table('t')`
still returns the stale False — a fresh `sa.inspect()` call correctly
returns True). If a migration issues DDL between two checks of the same
reflection type on the same table (e.g. create_table() then a later
has_index() on that table, which re-derives has_table() internally),
rebuild `insp = sa.inspect(op.get_bind())` after the DDL before the next
check — see 9100b1b36d72_add_fifo_consumptions_table.py's upgrade() for
the pattern.

IMPORTING THIS MODULE: every caller does
`from src.core.migration_utils import ...` *inside* upgrade()/
downgrade(), never at module level. Alembic's own file-discovery step —
which runs for every CLI command (`heads`, `history`, `upgrade`, ...),
not just the migration actually being applied — loads every file in
alembic/versions/ *before* env.py's `sys.path` fix runs. A top-level
import here would make every one of those commands fail outright with
ModuleNotFoundError. By the time a migration's upgrade()/downgrade()
function body actually executes (only ever called from within env.py's
run_migrations()), sys.path already has the backend root on it, so a
deferred, function-body-local import is safe.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Inspector


def has_table(table: str, insp: Inspector | None = None) -> bool:
    insp = insp or sa.inspect(op.get_bind())
    return insp.has_table(table)


def has_column(table: str, column: str, insp: Inspector | None = None) -> bool:
    insp = insp or sa.inspect(op.get_bind())
    if not has_table(table, insp=insp):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def has_constraint(table: str, name: str, insp: Inspector | None = None) -> bool:
    insp = insp or sa.inspect(op.get_bind())
    if not has_table(table, insp=insp):
        return False
    names = {c["name"] for c in insp.get_unique_constraints(table)}
    names |= {c["name"] for c in insp.get_foreign_keys(table)}
    return name in names


def has_index(table: str, name: str, insp: Inspector | None = None) -> bool:
    insp = insp or sa.inspect(op.get_bind())
    if not has_table(table, insp=insp):
        return False
    return name in {i["name"] for i in insp.get_indexes(table)}
