"""add business_id to usd_strategy_configs

Revision ID: 1bc1d54c112d
Revises: db06ca99f1fa
Create Date: 2026-09-10 14:04:29.955122

USDStrategyConfig (USD hedging/liquidity strategy configuration) has never
had a business_id column -- missed by the codebase-wide cross-tenant audit
(tasks 202-210, PRs #362-374) because the CI cross-tenant regression job
only runs tests matching cross_tenant|business_isolation|tenant_isolation,
and none existed for this table (task 213). Any authenticated user from
Business A could read and overwrite Business B's USD strategy config.

Idempotent (existence-checked per statement), matching the established
pattern for this exact shape of change -- see
1a76f66ca128_add_business_id_to_fx_exposures.py.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '1bc1d54c112d'
down_revision: Union[str, None] = 'db06ca99f1fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from src.core.migration_utils import has_column, has_constraint, has_index

    # Snapshot taken before any DDL below -- deciding what to do off this
    # pre-migration state avoids the Inspector staleness pitfall documented
    # in migration_utils.py.
    insp = sa.inspect(op.get_bind())
    usd_strategy_config_cols = {
        c["name"]: c for c in insp.get_columns("usd_strategy_configs")
    }

    if "business_id" not in usd_strategy_config_cols:
        op.add_column(
            "usd_strategy_configs",
            sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

    if (
        "business_id" not in usd_strategy_config_cols
        or usd_strategy_config_cols["business_id"]["nullable"]
    ):
        op.execute(
            "UPDATE usd_strategy_configs SET business_id = "
            "(SELECT id FROM businesses ORDER BY created_at LIMIT 1) "
            "WHERE business_id IS NULL"
        )
        op.alter_column("usd_strategy_configs", "business_id", nullable=False)

    if not has_constraint(
        "usd_strategy_configs", "fk_usd_strategy_configs_business_id", insp=insp
    ):
        op.create_foreign_key(
            "fk_usd_strategy_configs_business_id",
            "usd_strategy_configs",
            "businesses",
            ["business_id"],
            ["id"],
        )
    if not has_index(
        "usd_strategy_configs", "ix_usd_strategy_configs_business_id", insp=insp
    ):
        op.create_index(
            "ix_usd_strategy_configs_business_id",
            "usd_strategy_configs",
            ["business_id"],
        )


def downgrade() -> None:
    from src.core.migration_utils import has_column, has_constraint, has_index

    insp = sa.inspect(op.get_bind())

    if has_index(
        "usd_strategy_configs", "ix_usd_strategy_configs_business_id", insp=insp
    ):
        op.drop_index(
            "ix_usd_strategy_configs_business_id", table_name="usd_strategy_configs"
        )
    if has_constraint(
        "usd_strategy_configs", "fk_usd_strategy_configs_business_id", insp=insp
    ):
        op.drop_constraint(
            "fk_usd_strategy_configs_business_id",
            "usd_strategy_configs",
            type_="foreignkey",
        )
    if has_column("usd_strategy_configs", "business_id", insp=insp):
        op.drop_column("usd_strategy_configs", "business_id")
