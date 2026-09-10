"""add import_error to migration_jobs

Revision ID: e580169665df
Revises: 1bc1d54c112d
Create Date: 2026-09-10 14:48:31.996267

Task 215 moved confirm_job()'s heavy extract/transform/load/recompute work
into a background task so a realistically-sized historical import doesn't
hang past gunicorn's --timeout. Background failures can no longer become
a synchronous HTTP error response, so this column carries a client-safe
failure message (never the raw exception) for the frontend to display
while polling.

Idempotent (existence-checked), matching the established pattern for this
shape of change -- see 1bc1d54c112d_add_business_id_to_usd_strategy_configs.py.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e580169665df'
down_revision: Union[str, None] = '1bc1d54c112d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from src.core.migration_utils import has_column

    if not has_column("migration_jobs", "import_error"):
        op.add_column(
            "migration_jobs",
            sa.Column("import_error", sa.String(length=1000), nullable=True),
        )


def downgrade() -> None:
    from src.core.migration_utils import has_column

    if has_column("migration_jobs", "import_error"):
        op.drop_column("migration_jobs", "import_error")
