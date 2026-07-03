"""add business_id to stress_scenarios

Revision ID: 4def4e1d8faf
Revises: d0679eb1beff
Create Date: 2026-07-03 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "4def4e1d8faf"
down_revision = "d0679eb1beff"
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
    op.execute(
        "UPDATE stress_scenarios SET business_id = "
        "(SELECT id FROM businesses ORDER BY created_at LIMIT 1) "
        "WHERE business_id IS NULL"
    )
    op.alter_column("stress_scenarios", "business_id", nullable=False)
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
