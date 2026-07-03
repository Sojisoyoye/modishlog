"""add business_id to stress_scenarios

Revision ID: a1b2c3d4e5f6
Revises: fc51a3928318
Create Date: 2026-07-03 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "fc51a3928318"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stress_scenarios",
        sa.Column(
            "business_id",
            sa.Uuid(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_stress_scenarios_business_id",
        "stress_scenarios",
        ["business_id"],
    )
    op.create_foreign_key(
        "fk_stress_scenarios_business_id",
        "stress_scenarios",
        "businesses",
        ["business_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_stress_scenarios_business_id", "stress_scenarios", type_="foreignkey"
    )
    op.drop_index("ix_stress_scenarios_business_id", table_name="stress_scenarios")
    op.drop_column("stress_scenarios", "business_id")
