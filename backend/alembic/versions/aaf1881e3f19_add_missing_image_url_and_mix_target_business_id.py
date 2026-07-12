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


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _has_constraint(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    names = {c["name"] for c in insp.get_unique_constraints(table)}
    names |= {c["name"] for c in insp.get_foreign_keys(table)}
    return name in names


def _has_index(table: str, name: str) -> bool:
    return name in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    if not _has_column("products", "image_url"):
        op.add_column("products", sa.Column("image_url", sa.String(500), nullable=True))

    if not _has_column("product_mix_targets", "business_id"):
        op.add_column(
            "product_mix_targets",
            sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.execute(
            "UPDATE product_mix_targets SET business_id = "
            "(SELECT id FROM businesses ORDER BY created_at LIMIT 1) "
            "WHERE business_id IS NULL"
        )
        op.alter_column("product_mix_targets", "business_id", nullable=False)

    if not _has_constraint("product_mix_targets", "fk_product_mix_targets_business_id"):
        op.create_foreign_key(
            "fk_product_mix_targets_business_id",
            "product_mix_targets",
            "businesses",
            ["business_id"],
            ["id"],
        )
    if not _has_index("product_mix_targets", "ix_product_mix_targets_business_id"):
        op.create_index(
            "ix_product_mix_targets_business_id", "product_mix_targets", ["business_id"]
        )
    if not _has_constraint("product_mix_targets", "uq_mix_target_category_business"):
        op.create_unique_constraint(
            "uq_mix_target_category_business",
            "product_mix_targets",
            ["category_id", "business_id"],
        )


def downgrade() -> None:
    op.drop_constraint(
        "uq_mix_target_category_business", "product_mix_targets", type_="unique"
    )
    op.drop_index("ix_product_mix_targets_business_id", table_name="product_mix_targets")
    op.drop_constraint(
        "fk_product_mix_targets_business_id", "product_mix_targets", type_="foreignkey"
    )
    op.drop_column("product_mix_targets", "business_id")

    op.drop_column("products", "image_url")
