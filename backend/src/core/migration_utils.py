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
"""

import sqlalchemy as sa
from alembic import op


def has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def has_column(table: str, column: str) -> bool:
    if not has_table(table):
        return False
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def has_constraint(table: str, name: str) -> bool:
    if not has_table(table):
        return False
    insp = sa.inspect(op.get_bind())
    names = {c["name"] for c in insp.get_unique_constraints(table)}
    names |= {c["name"] for c in insp.get_foreign_keys(table)}
    return name in names


def has_index(table: str, name: str) -> bool:
    if not has_table(table):
        return False
    return name in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}
