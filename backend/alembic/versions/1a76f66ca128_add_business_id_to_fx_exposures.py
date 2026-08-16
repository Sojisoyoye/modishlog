"""add business_id to fx_exposures

Revision ID: 1a76f66ca128
Revises: 4947af767e2a
Create Date: 2026-08-16 09:22:02.579725

FXExposure (currency hedge position tracking) has never had a
business_id column, unlike its siblings FXExposureConfig/FXAlert in the
same file -- found in a codebase-wide cross-tenant audit (task 209).
Every business's real hedge positions (locked amounts, locked rates,
unrealized P&L) were visible/lockable across every tenant.

Idempotent (existence-checked per statement), matching the established
pattern for this exact shape of change -- see
aaf1881e3f19_add_missing_image_url_and_mix_target_business_id.py and
4def4e1d8faf_add_business_id_to_stress_scenarios.py.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '1a76f66ca128'
down_revision: Union[str, None] = '4947af767e2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from src.core.migration_utils import has_column, has_constraint, has_index

    # Snapshot taken before any DDL below -- deciding what to do off this
    # pre-migration state avoids the Inspector staleness pitfall documented
    # in migration_utils.py (re-querying the same insp for the same
    # reflection type right after issuing DDL can return cached pre-DDL
    # results). Matches aaf1881e3f19's approach for this exact shape of
    # change.
    insp = sa.inspect(op.get_bind())
    fx_exposure_cols = {c["name"]: c for c in insp.get_columns("fx_exposures")}

    if "business_id" not in fx_exposure_cols:
        op.add_column(
            "fx_exposures",
            sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

    if (
        "business_id" not in fx_exposure_cols
        or fx_exposure_cols["business_id"]["nullable"]
    ):
        op.execute(
            "UPDATE fx_exposures SET business_id = "
            "(SELECT id FROM businesses ORDER BY created_at LIMIT 1) "
            "WHERE business_id IS NULL"
        )
        op.alter_column("fx_exposures", "business_id", nullable=False)

    if not has_constraint("fx_exposures", "fk_fx_exposures_business_id", insp=insp):
        op.create_foreign_key(
            "fk_fx_exposures_business_id",
            "fx_exposures",
            "businesses",
            ["business_id"],
            ["id"],
        )
    if not has_index("fx_exposures", "ix_fx_exposures_business_id", insp=insp):
        op.create_index(
            "ix_fx_exposures_business_id", "fx_exposures", ["business_id"]
        )


def downgrade() -> None:
    from src.core.migration_utils import has_column, has_constraint, has_index

    insp = sa.inspect(op.get_bind())

    if has_index("fx_exposures", "ix_fx_exposures_business_id", insp=insp):
        op.drop_index("ix_fx_exposures_business_id", table_name="fx_exposures")
    if has_constraint("fx_exposures", "fk_fx_exposures_business_id", insp=insp):
        op.drop_constraint(
            "fk_fx_exposures_business_id", "fx_exposures", type_="foreignkey"
        )
    if has_column("fx_exposures", "business_id", insp=insp):
        op.drop_column("fx_exposures", "business_id")
