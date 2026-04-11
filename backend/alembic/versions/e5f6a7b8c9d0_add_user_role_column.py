"""add user role column

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-10 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the enum type first
    userrole_enum = sa.Enum("admin", "sales_manager", name="userrole")
    userrole_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "users",
        sa.Column(
            "role",
            userrole_enum,
            server_default="admin",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "role")

    # Drop the enum type
    userrole_enum = sa.Enum("admin", "sales_manager", name="userrole")
    userrole_enum.drop(op.get_bind(), checkfirst=True)
