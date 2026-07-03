"""add business_id to domain tables

Revision ID: d0679eb1beff
Revises: 9507112c79f3
Create Date: 2026-07-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'd0679eb1beff'
down_revision = '9507112c79f3'
branch_labels = None
depends_on = None

# Tables that get a direct business_id column.
# Ordered so dependent tables come after their parents (no FK ordering issues here
# since business_id always references the same `businesses` table).
DOMAIN_TABLES = [
    "products",
    "product_categories",
    "customers",
    "business_locations",
    "suppliers",
    "sales",
    "sell_returns",
    "sale_bulk_upload_jobs",
    "stock_counts",
    "purchase_orders",
    "purchase_returns",
    "expenses",
    "expense_categories",
    "operating_costs",
    "cashflow_projections",
    "loan_obligations",
    "triage_records",
    "fx_alerts",
    "fx_exposure_configs",
    "ai_recommendations",
    "reorder_suggestions",
    "reorder_configs",
    "pricing_recommendations",
    "margin_targets",
    "pricing_scenarios",
    "invoice_schemes",
    "pos_sync_state",
    "business_profile",
    "app_settings",
]

# Tables that have no `created_at` column — backfill without ORDER BY.
NO_CREATED_AT = {"pos_sync_state", "app_settings"}


def upgrade() -> None:
    for table in DOMAIN_TABLES:
        # Add nullable first so existing rows can be backfilled.
        op.add_column(
            table,
            sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

        # Backfill existing rows to the first (and only) business.
        if table in NO_CREATED_AT:
            op.execute(
                f"UPDATE {table} SET business_id = (SELECT id FROM businesses LIMIT 1) "
                f"WHERE business_id IS NULL"
            )
        else:
            op.execute(
                f"UPDATE {table} SET business_id = "
                f"(SELECT id FROM businesses ORDER BY created_at LIMIT 1) "
                f"WHERE business_id IS NULL"
            )

        # Enforce NOT NULL after backfill.
        op.alter_column(table, "business_id", nullable=False)

        # FK constraint to businesses.
        op.create_foreign_key(
            f"fk_{table}_business_id",
            table,
            "businesses",
            ["business_id"],
            ["id"],
        )

        # Index for fast tenant-scoped queries.
        op.create_index(f"ix_{table}_business_id", table, ["business_id"])

    # product_categories.name was globally unique; make it per-business instead.
    op.drop_constraint("product_categories_name_key", "product_categories", type_="unique")
    op.create_unique_constraint(
        "uq_product_categories_name_business",
        "product_categories",
        ["name", "business_id"],
    )

    # business_profile: enforce one row per business.
    op.create_unique_constraint(
        "uq_business_profile_business_id",
        "business_profile",
        ["business_id"],
    )

    # app_settings: the original PK is single-column (key only). Promote it to a
    # composite PK (key, business_id) to match the updated ORM model. We must drop
    # the old PK first, then create the new composite one.
    op.drop_constraint("app_settings_pkey", "app_settings", type_="primary")
    op.create_primary_key("app_settings_pkey", "app_settings", ["key", "business_id"])
    # The model also declares a named UniqueConstraint on (key, business_id); the
    # composite PK already enforces that invariant but the ORM metadata needs the
    # constraint present under its declared name so autogenerate stays clean.
    op.create_unique_constraint(
        "uq_app_settings_key_business_id",
        "app_settings",
        ["key", "business_id"],
    )


def downgrade() -> None:
    # Remove unique constraints added in upgrade.
    op.drop_constraint("uq_app_settings_key_business_id", "app_settings", type_="unique")
    # Restore app_settings primary key to single-column (key only).
    op.drop_constraint("app_settings_pkey", "app_settings", type_="primary")
    op.create_primary_key("app_settings_pkey", "app_settings", ["key"])
    op.drop_constraint("uq_business_profile_business_id", "business_profile", type_="unique")
    op.drop_constraint(
        "uq_product_categories_name_business", "product_categories", type_="unique"
    )
    op.create_unique_constraint(
        "product_categories_name_key", "product_categories", ["name"]
    )

    for table in reversed(DOMAIN_TABLES):
        op.drop_index(f"ix_{table}_business_id", table_name=table)
        op.drop_constraint(f"fk_{table}_business_id", table, type_="foreignkey")
        op.drop_column(table, "business_id")
