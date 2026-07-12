"""add_data_import_migration_jobs

Revision ID: bc0d9bce053d
Revises: f1e2d3c4b5a6
Create Date: 2026-07-10 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "bc0d9bce053d"
down_revision: Union[str, None] = "f1e2d3c4b5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every table an ETL import job can tag rows in. migration_id stays nullable —
# the overwhelming majority of rows are never migration-sourced, so there's
# nothing to backfill.
MIGRATION_ID_TABLES = [
    "products",
    "product_variants",
    "product_categories",
    "customers",
    "suppliers",
    "supplier_products",
    "sales",
    "sell_returns",
    "sale_audit_entries",
    "purchase_orders",
    "order_line_items",
    "order_payments",
    "order_status_history",
    "inventory_levels",
    "inventory_batches",
    "stock_movements",
    "expenses",
    "expense_categories",
    "price_history",
    "stock_counts",
    "stock_count_items",
    "business_locations",
    "users",
]

migration_job_status = postgresql.ENUM(
    "pending",
    "extracting",
    "transforming",
    "awaiting_confirmation",
    "importing",
    "recomputing",
    "done",
    "failed",
    "cancelled",
    "rolled_back",
    name="migrationjobstatus",
)
source_system = postgresql.ENUM(
    "ultimatepos", "quickbooks", "shopify", "generic", name="sourcesystem"
)
extraction_mode = postgresql.ENUM("csv", "api", name="extractionmode")


def upgrade() -> None:
    # Deferred, not module-level — see src/core/migration_utils.py's
    # docstring ("IMPORTING THIS MODULE") for why.
    from src.core.migration_utils import (
        has_column,
        has_constraint,
        has_index,
        has_table,
    )

    insp = sa.inspect(op.get_bind())

    # The enum types are created implicitly as part of create_table below (each
    # is referenced by a column) — an explicit .create() first would collide
    # with that and raise DuplicateObjectError. Guarding create_table on
    # has_table() also protects the enum-type creation: if the table already
    # exists, the types created alongside it in a prior (untracked) run do too.
    if not has_table("migration_jobs", insp=insp):
        op.create_table(
            "migration_jobs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.Column(
                "business_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("businesses.id"),
                nullable=False,
            ),
            sa.Column("status", migration_job_status, nullable=False),
            sa.Column("source_system", source_system, nullable=False),
            sa.Column("extraction_mode", extraction_mode, nullable=False),
            sa.Column("api_base_url", sa.String(500), nullable=True),
            sa.Column(
                "checkpoint", postgresql.JSONB, nullable=False, server_default="{}"
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "row_counts", postgresql.JSONB, nullable=False, server_default="{}"
            ),
            sa.Column(
                "validation_errors",
                postgresql.JSONB,
                nullable=False,
                server_default="[]",
            ),
            sa.Column(
                "validation_warnings",
                postgresql.JSONB,
                nullable=False,
                server_default="[]",
            ),
            sa.Column("options", postgresql.JSONB, nullable=False, server_default="{}"),
            sa.Column(
                "created_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
        )
        # SQLAlchemy's Inspector caches has_table()/get_indexes() results
        # per-instance — reusing `insp` after create_table() just ran would
        # make the has_index() check below see the pre-creation state.
        insp = sa.inspect(op.get_bind())
    if not has_index("migration_jobs", "ix_migration_jobs_business_id", insp=insp):
        op.create_index(
            "ix_migration_jobs_business_id", "migration_jobs", ["business_id"]
        )

    for table in MIGRATION_ID_TABLES:
        if not has_column(table, "migration_id", insp=insp):
            op.add_column(
                table,
                sa.Column("migration_id", postgresql.UUID(as_uuid=True), nullable=True),
            )
        if not has_constraint(table, f"fk_{table}_migration_id", insp=insp):
            op.create_foreign_key(
                f"fk_{table}_migration_id",
                table,
                "migration_jobs",
                ["migration_id"],
                ["id"],
            )
        if not has_index(table, f"ix_{table}_migration_id", insp=insp):
            op.create_index(f"ix_{table}_migration_id", table, ["migration_id"])


def downgrade() -> None:
    from src.core.migration_utils import (
        has_column,
        has_constraint,
        has_index,
        has_table,
    )

    insp = sa.inspect(op.get_bind())

    for table in reversed(MIGRATION_ID_TABLES):
        if has_index(table, f"ix_{table}_migration_id", insp=insp):
            op.drop_index(f"ix_{table}_migration_id", table_name=table)
        if has_constraint(table, f"fk_{table}_migration_id", insp=insp):
            op.drop_constraint(f"fk_{table}_migration_id", table, type_="foreignkey")
        if has_column(table, "migration_id", insp=insp):
            op.drop_column(table, "migration_id")

    if has_index("migration_jobs", "ix_migration_jobs_business_id", insp=insp):
        op.drop_index("ix_migration_jobs_business_id", table_name="migration_jobs")
    if has_table("migration_jobs", insp=insp):
        op.drop_table("migration_jobs")

    bind = op.get_bind()
    extraction_mode.drop(bind, checkfirst=True)
    source_system.drop(bind, checkfirst=True)
    migration_job_status.drop(bind, checkfirst=True)
