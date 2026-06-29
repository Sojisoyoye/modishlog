"""add_user_preferences_table

Revision ID: a2b3c4d5e6f7
Revises: f9a0b1c2d3e4
Create Date: 2026-06-29 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("fiscal_year_start_month", sa.Integer(), nullable=True),
        sa.Column("fiscal_year_start_day", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # UniqueConstraint implicitly creates a unique index on user_id in PostgreSQL;
        # no separate create_index needed.
        sa.UniqueConstraint("user_id", name="uq_user_preferences_user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
