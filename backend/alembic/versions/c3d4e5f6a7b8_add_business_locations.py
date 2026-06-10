"""add_business_locations

Revision ID: c3d4e5f6a7b8
Revises: a8b9c0d1e2f3
Create Date: 2026-06-10 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "business_locations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("location_code", sa.String(length=20), nullable=False),
        sa.Column("mobile", sa.String(length=50), nullable=True),
        sa.Column("alternate_number", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("website", sa.String(length=255), nullable=True),
        sa.Column("landmark", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("zip_code", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("location_code", name="uq_business_locations_location_code"),
    )
    op.create_index(
        op.f("ix_business_locations_name"), "business_locations", ["name"], unique=False
    )
    op.create_index(
        op.f("ix_business_locations_location_code"),
        "business_locations",
        ["location_code"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_business_locations_location_code"), table_name="business_locations"
    )
    op.drop_index(op.f("ix_business_locations_name"), table_name="business_locations")
    op.drop_table("business_locations")
