"""add_variant_id_to_price_suggestions

Revision ID: 78362e79f979
Revises: fdb77f054f7e
Create Date: 2026-07-12 12:30:00.000000

Made idempotent — see migration aaf1881e3f19 and
src/core/migration_utils.py for why: staging/prod's actual schema can
drift ahead of alembic_version, and this migration must self-heal rather
than hard-fail with DuplicateColumnError if that's already happened here.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "78362e79f979"
down_revision: Union[str, None] = "fdb77f054f7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Deferred, not module-level — see 00db7d1e1a78's upgrade() comment:
    # Alembic's own file-discovery loads every versions file before
    # env.py's sys.path fix runs, so a top-level `from src...` import
    # here would break `alembic heads`/`history`/`upgrade` outright.
    from src.core.migration_utils import has_column, has_constraint, has_index

    if not has_column("price_suggestions", "variant_id"):
        op.add_column(
            "price_suggestions",
            sa.Column(
                "variant_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
    if not has_constraint("price_suggestions", "fk_price_suggestions_variant_id"):
        op.create_foreign_key(
            "fk_price_suggestions_variant_id",
            "price_suggestions",
            "product_variants",
            ["variant_id"],
            ["id"],
        )
    if not has_index("price_suggestions", "ix_price_suggestions_variant_id"):
        op.create_index(
            "ix_price_suggestions_variant_id", "price_suggestions", ["variant_id"]
        )


def downgrade() -> None:
    from src.core.migration_utils import has_column, has_constraint, has_index

    if has_index("price_suggestions", "ix_price_suggestions_variant_id"):
        op.drop_index(
            "ix_price_suggestions_variant_id", table_name="price_suggestions"
        )
    if has_constraint("price_suggestions", "fk_price_suggestions_variant_id"):
        op.drop_constraint(
            "fk_price_suggestions_variant_id", "price_suggestions", type_="foreignkey"
        )
    if has_column("price_suggestions", "variant_id"):
        op.drop_column("price_suggestions", "variant_id")
