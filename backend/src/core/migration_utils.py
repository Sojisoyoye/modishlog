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
call, rather than letting each call construct (and re-run has_table()
against) its own — up to 6 redundant catalog round-trips otherwise for a
single migration that checks a column, a constraint, and an index.
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
