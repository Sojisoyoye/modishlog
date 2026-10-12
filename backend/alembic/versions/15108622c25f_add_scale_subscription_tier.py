"""add_scale_subscription_tier

Revision ID: 15108622c25f
Revises: 0600a3b57678
Create Date: 2026-10-10 09:14:16.031466

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15108622c25f'
down_revision: Union[str, None] = '0600a3b57678'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres forbids using a new enum value in the same transaction that
    # adds it -- keep this migration to exactly this one statement so no
    # later migration in the same run can accidentally violate that.
    op.execute("ALTER TYPE subscriptiontier ADD VALUE IF NOT EXISTS 'scale'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for enums -- removing one cleanly requires
    # recreating the type (rename old, create a 2-value type, migrate the
    # column, drop old) and rewriting every row currently using it. Not
    # implemented: no production business uses 'scale' yet (task #267), so
    # this risk is accepted rather than built out speculatively.
    raise NotImplementedError(
        "Cannot cleanly downgrade: Postgres has no DROP VALUE for enums. "
        "See this migration's docstring/comment for what a real downgrade would require."
    )
