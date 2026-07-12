"""add_missing_image_url_and_mix_target_business_id

Revision ID: aaf1881e3f19
Revises: 5b084b6ad359
Create Date: 2026-07-10 22:45:00.000000

Both columns are declared on their ORM models (products.image_url since the
image-upload feature, product_mix_targets.business_id since the business_id
isolation migration d0679eb1beff) but were never actually added to the
schema — product_mix_targets was missed from d0679eb1beff's DOMAIN_TABLES
list, and no migration for image_url was ever written. Any fresh database
(a new dev/test/prod instance migrated from scratch) is missing both.

Made idempotent (existence-checked per statement) after discovering staging
and prod had `products.image_url` backfilled directly via emergency raw SQL
(`fix-staging.yml`/`fix-prod-schema.yml`'s `ADD COLUMN IF NOT EXISTS`) before
this migration ever ran through real `alembic upgrade head` tracking —
CI only exercises pytest against a freshly-created schema, never runs
`alembic upgrade head` itself, so this plain (non-idempotent) version had
never actually succeeded against a real environment. Without these guards,
`alembic upgrade head` fails with DuplicateColumnError on `products.image_url`
and permanently blocks every migration after this one.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'aaf1881e3f19'
down_revision: Union[str, None] = '5b084b6ad359'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Deferred, not module-level — see 00db7d1e1a78's upgrade() comment
    # (src/core/migration_utils.py wasn't extracted until task 165's
    # follow-up migrations; this is the migration that motivated it):
    # Alembic's own file-discovery loads every versions file before
    # env.py's sys.path fix runs, so a top-level `from src...` import
    # here would break `alembic heads`/`history`/`upgrade` outright.
    from src.core.migration_utils import has_column, has_constraint, has_index

    # One inspection, reused for every check below — six separate
    # sa.inspect(op.get_bind()) calls would mean six real round-trips to
    # Postgres for a migration that already has a history of blocking
    # every deploy behind it if it's slow or fails.
    insp = sa.inspect(op.get_bind())
    mix_target_cols = {c["name"]: c for c in insp.get_columns("product_mix_targets")}

    if not has_column("products", "image_url", insp=insp):
        op.add_column("products", sa.Column("image_url", sa.String(500), nullable=True))

    if "business_id" not in mix_target_cols:
        op.add_column(
            "product_mix_targets",
            sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

    # Backfill + NOT NULL enforcement run whenever the column is still
    # nullable — covers both "just added above" and "the column exists
    # but was never finalized" (e.g. a prior migration attempt that
    # failed partway through, or some other partial manual fix). Column
    # *existence* alone is not "already done": a drifted DB could have
    # the column with every row still NULL. has_column() can't express
    # this (existence only), so this check stays bespoke rather than
    # using the shared helper.
    if "business_id" not in mix_target_cols or mix_target_cols["business_id"]["nullable"]:
        op.execute(
            "UPDATE product_mix_targets SET business_id = "
            "(SELECT id FROM businesses ORDER BY created_at LIMIT 1) "
            "WHERE business_id IS NULL"
        )
        op.alter_column("product_mix_targets", "business_id", nullable=False)

    if not has_constraint(
        "product_mix_targets", "fk_product_mix_targets_business_id", insp=insp
    ):
        op.create_foreign_key(
            "fk_product_mix_targets_business_id",
            "product_mix_targets",
            "businesses",
            ["business_id"],
            ["id"],
        )
    if not has_index(
        "product_mix_targets", "ix_product_mix_targets_business_id", insp=insp
    ):
        op.create_index(
            "ix_product_mix_targets_business_id", "product_mix_targets", ["business_id"]
        )
    if not has_constraint(
        "product_mix_targets", "uq_mix_target_category_business", insp=insp
    ):
        op.create_unique_constraint(
            "uq_mix_target_category_business",
            "product_mix_targets",
            ["category_id", "business_id"],
        )


def downgrade() -> None:
    # Idempotent for the same reason upgrade() is: this migration may
    # have partially (or fully) no-op'd against a drifted DB, so a plain
    # unconditional drop_* sequence could hit an UndefinedColumn/
    # ProgrammingError partway through and leave the DB half-reverted.
    from src.core.migration_utils import has_column, has_constraint, has_index

    insp = sa.inspect(op.get_bind())

    if has_constraint(
        "product_mix_targets", "uq_mix_target_category_business", insp=insp
    ):
        op.drop_constraint(
            "uq_mix_target_category_business", "product_mix_targets", type_="unique"
        )
    if has_index(
        "product_mix_targets", "ix_product_mix_targets_business_id", insp=insp
    ):
        op.drop_index(
            "ix_product_mix_targets_business_id", table_name="product_mix_targets"
        )
    if has_constraint(
        "product_mix_targets", "fk_product_mix_targets_business_id", insp=insp
    ):
        op.drop_constraint(
            "fk_product_mix_targets_business_id",
            "product_mix_targets",
            type_="foreignkey",
        )
    if has_column("product_mix_targets", "business_id", insp=insp):
        op.drop_column("product_mix_targets", "business_id")

    if has_column("products", "image_url", insp=insp):
        op.drop_column("products", "image_url")
