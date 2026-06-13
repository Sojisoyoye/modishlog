"""add_slug_to_products

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-06-13 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("slug", sa.String(255), nullable=True))

    # Populate slug for all existing products using the same rules as slugify():
    # 1. Replace × (U+00D7) and * with x
    # 2. Lowercase
    # 3. Spaces → hyphens
    # 4. Strip non-alphanumeric/non-hyphen chars (removes dots etc.)
    # 5. Collapse multiple hyphens
    # 6. Trim leading/trailing hyphens
    #
    # For duplicate base slugs (same-name products), append a sequential suffix
    # (-1, -2 …) ordered by created_at so the oldest product keeps the clean slug.
    op.execute(
        """
        WITH base AS (
            SELECT id,
                   trim(both '-' from
                       regexp_replace(
                           regexp_replace(
                               regexp_replace(
                                   lower(
                                       replace(replace(name, '×', 'x'), '*', 'x')
                                   ),
                                   '\\s+', '-', 'g'
                               ),
                               '[^a-z0-9\\-]', '', 'g'
                           ),
                           '-+', '-', 'g'
                       )
                   ) AS base_slug
            FROM products
        ),
        ranked AS (
            SELECT id,
                   base_slug,
                   ROW_NUMBER() OVER (
                       PARTITION BY base_slug ORDER BY
                           (SELECT created_at FROM products p WHERE p.id = base.id),
                           id
                   ) - 1 AS n
            FROM base
        )
        UPDATE products p
        SET slug = CASE
            WHEN r.n = 0 THEN r.base_slug
            ELSE r.base_slug || '-' || r.n::text
        END
        FROM ranked r
        WHERE p.id = r.id
        """
    )

    op.alter_column("products", "slug", nullable=False)
    op.create_unique_constraint("uq_products_slug", "products", ["slug"])
    op.create_index("ix_products_slug", "products", ["slug"])


def downgrade() -> None:
    op.drop_index("ix_products_slug", table_name="products")
    op.drop_constraint("uq_products_slug", "products", type_="unique")
    op.drop_column("products", "slug")
