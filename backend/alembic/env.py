"""Alembic environment configuration for async migrations."""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

# Ensure the backend package root is on sys.path so `src.*` imports resolve.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.core.config import settings
from src.core.database import Base

# Import all models so Alembic can detect them
from src.auth.models import User, PasswordResetToken  # noqa: F401
from src.products.models import Product, ProductCategory, PriceHistory  # noqa: F401
from src.inventory.models import InventoryLevel, StockMovement, LowStockAlert  # noqa: F401
from src.sales.models import Sale, SaleBulkUploadJob, SaleAuditEntry, SellReturn  # noqa: F401
from src.orders.models import (  # noqa: F401
    PurchaseOrder,
    OrderLineItem,
    OrderStatusHistory,
    OrderPayment,
    PurchaseReturn,
)
from src.locations.models import BusinessLocation, LocationType  # noqa: F401
from src.settings.models import BusinessProfile, AppSetting  # noqa: F401
from src.suppliers.models import Supplier, SupplierProduct  # noqa: F401
from src.customers.models import Customer  # noqa: F401
from src.fx.models import (  # noqa: F401
    FXRate,
    FXExposure,
    FXExposureConfig,
    FXAlert,
    FXSimulationRun,
)
from src.cashflow.models import (  # noqa: F401
    CashflowProjection,
    ProjectionAssumptions,
    DSCRRecord,
    LoanObligation,
    LoanPaymentSchedule,
    StressScenario,
    TriageRecord,
)
from src.pricing.models import (  # noqa: F401
    DemandElasticity,
    MarginTarget,
    PricingRecommendation,
    ProductMixTarget,
    CrossSubsidyAnalysis,
)
from src.expenses.models import Expense, ExpenseCategory  # noqa: F401
from src.pos_sync.models import SyncState  # noqa: F401
from src.ai_engine.models import (  # noqa: F401
    AIRecommendation,
    USDStrategyConfig,
    USDPurchaseSchedule,
    ReorderSuggestion,
    ReorderConfig,
)
from src.data_import.models import MigrationJob  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Offline mode generates SQL scripts without opening a live connection,
    so connect_args (ssl=True) are intentionally omitted here.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connect_args = {"ssl": True} if settings.DATABASE_SSL else {}
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
