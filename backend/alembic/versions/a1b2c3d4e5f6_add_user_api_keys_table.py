"""add_user_api_keys_table

Revision ID: a1b2c3d4e5f6
Revises: f9a0b1c2d3e4
Create Date: 2026-06-12 20:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_api_keys",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("key_name", sa.String(100), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
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
    )
    op.create_index("ix_user_api_keys_user_id", "user_api_keys", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_api_keys_user_id", table_name="user_api_keys")
    op.drop_table("user_api_keys")
