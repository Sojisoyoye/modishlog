"""Reports domain business logic."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cashflow.models import OperatingCost
from src.inventory.models import InventoryBatch, InventoryLevel
from src.orders.models import OrderPayment, OrderPaymentStatus, PurchaseOrder, PurchaseReturn
from src.products.models import Product, ProductCategory
from src.reports.schemas import (
    ProfitLossReport,
    PurchaseSaleReport,
    StockReport,
    StockReportItem,
)
from src.sales.models import Sale, SaleStatus, SellReturn
from src.settings.service import get_fiscal_year_start

logger = structlog.get_logger()


async def resolve_default_date_range(
    db: AsyncSession,
    user_id: uuid.UUID,
    today: date | None = None,
) -> tuple[date, date]:
    """Return (date_from, date_to) for reports when no explicit dates are supplied.

    Uses the configured fiscal year start to compute the most recent FY start ≤ today.
    Falls back to (today - 365 days, today) when no FY is configured.
    """
    effective_today = today if today is not None else date.today()
    logger.info(
        "resolving_default_date_range", user_id=user_id, effective_today=effective_today
    )
    fy = await get_fiscal_year_start(db, user_id)

    if fy.fiscal_year_start_month is None or fy.fiscal_year_start_day is None:
        return effective_today - timedelta(days=365), effective_today

    month = fy.fiscal_year_start_month
    day = fy.fiscal_year_start_day
    fys_this_year = date(effective_today.year, month, day)
    if fys_this_year <= effective_today:
        return fys_this_year, effective_today
    return date(effective_today.year - 1, month, day), effective_today


async def _sum_sell_returns(
    db: AsyncSession,
    start_date: date | None,
    end_date: date | None,
) -> Decimal:
    q = select(func.sum(SellReturn.total_amount))
    if start_date:
        q = q.where(SellReturn.return_date >= start_date)
    if end_date:
        q = q.where(SellReturn.return_date <= end_date)
    result = await db.execute(q)
    return result.scalar() or Decimal("0")


async def get_profit_loss_report(
    db: AsyncSession,
    start_date: date | None = None,
    end_date: date | None = None,
) -> ProfitLossReport:
    """Calculate profit and loss report for an optional date range.

    Args:
        db: Async database session.
        start_date: Start of reporting period (inclusive). None means all time.
        end_date: End of reporting period (inclusive). None means all time.

    Returns:
        ProfitLossReport with all computed fields.
    """
    logger.info(
        "generating profit_loss_report", start_date=start_date, end_date=end_date
    )

    # -- Total purchases (sum of all purchase orders in period) --
    purchase_query = select(func.sum(PurchaseOrder.total_amount))
    if start_date:
        purchase_query = purchase_query.where(PurchaseOrder.created_at >= start_date)
    if end_date:
        purchase_query = purchase_query.where(PurchaseOrder.created_at <= end_date)
    purchase_result = await db.execute(purchase_query)
    total_purchase = purchase_result.scalar() or Decimal("0")

    # -- Total completed sales in period --
    sales_query = select(func.sum(Sale.total_amount)).where(
        Sale.status == SaleStatus.COMPLETED
    )
    if start_date:
        sales_query = sales_query.where(Sale.sale_date >= start_date)
    if end_date:
        sales_query = sales_query.where(Sale.sale_date <= end_date)
    sales_result = await db.execute(sales_query)
    total_sales = sales_result.scalar() or Decimal("0")

    # -- Operating costs (active only) --
    opex_query = select(OperatingCost).where(OperatingCost.is_active == True)  # noqa: E712
    opex_result = await db.execute(opex_query)
    operating_costs = opex_result.scalars().all()

    # Approximate months in period (default 1 month if no dates given)
    if start_date and end_date:
        delta_days = (end_date - start_date).days
        months = Decimal(str(max(1, delta_days / 30)))
    else:
        months = Decimal("1")

    total_operating_costs = (
        sum(
            (oc.monthly_equivalent for oc in operating_costs),
            Decimal("0"),
        )
        * months
    )

    # -- Current stock value (opening and closing use same query: current state) --
    stock_query = select(
        func.sum(
            InventoryBatch.quantity_remaining * InventoryBatch.landed_cost_per_unit
        )
    )
    stock_result = await db.execute(stock_query)
    stock_value = stock_result.scalar() or Decimal("0")

    # -- Purchase returns in period --
    returns_query = select(func.sum(PurchaseReturn.total_amount))
    if start_date:
        returns_query = returns_query.where(PurchaseReturn.return_date >= start_date)
    if end_date:
        returns_query = returns_query.where(PurchaseReturn.return_date <= end_date)
    returns_result = await db.execute(returns_query)
    purchase_returns_total = returns_result.scalar() or Decimal("0")

    # -- Sell returns in period --
    total_sales_returns = await _sum_sell_returns(db, start_date, end_date)

    # -- Purchase due: sum of outstanding balances on UNPAID/PARTIAL orders --
    paid_subq = (
        select(
            OrderPayment.order_id,
            func.sum(OrderPayment.amount).label("total_paid"),
        )
        .group_by(OrderPayment.order_id)
        .subquery()
    )
    purchase_due_query = (
        select(
            func.sum(
                PurchaseOrder.total_amount
                - func.coalesce(paid_subq.c.total_paid, 0)
            )
        )
        .outerjoin(paid_subq, paid_subq.c.order_id == PurchaseOrder.id)
        .where(
            PurchaseOrder.payment_status.in_(
                [OrderPaymentStatus.UNPAID, OrderPaymentStatus.PARTIAL]
            )
        )
    )
    if start_date:
        purchase_due_query = purchase_due_query.where(PurchaseOrder.created_at >= start_date)
    if end_date:
        purchase_due_query = purchase_due_query.where(PurchaseOrder.created_at <= end_date)
    purchase_due_result = await db.execute(purchase_due_query)
    purchase_due = purchase_due_result.scalar() or Decimal("0")

    # -- Sales due: sum of outstanding balances on credit/partial sales --
    sales_due_query = (
        select(
            func.sum(
                Sale.total_amount
                - func.coalesce(Sale.payment_amount, 0)
            )
        )
        .where(Sale.status == SaleStatus.COMPLETED)
        .where(Sale.payment_status.isnot(None))
        .where(Sale.payment_status != "paid")
    )
    if start_date:
        sales_due_query = sales_due_query.where(Sale.sale_date >= start_date)
    if end_date:
        sales_due_query = sales_due_query.where(Sale.sale_date <= end_date)
    sales_due_result = await db.execute(sales_due_query)
    sales_due = sales_due_result.scalar() or Decimal("0")

    gross_profit = total_sales - total_purchase
    net_profit = gross_profit - total_operating_costs

    return ProfitLossReport(
        total_purchase_excl_tax=total_purchase,
        purchase_returns_total=purchase_returns_total,
        total_sales=total_sales,
        gross_profit=gross_profit,
        total_operating_costs=total_operating_costs,
        net_profit=net_profit,
        opening_stock_value=stock_value,
        closing_stock_value=stock_value,
        total_sales_returns=total_sales_returns,
        purchase_due=purchase_due,
        sales_due=sales_due,
    )


async def get_stock_report(
    db: AsyncSession,
    category_id: str | None = None,
) -> StockReport:
    """Generate a stock report showing inventory levels and valuations.

    Args:
        db: Async database session.
        category_id: Optional UUID string to filter by product category.

    Returns:
        StockReport with per-product rows and aggregated totals.
    """
    logger.info("generating stock_report", category_id=category_id)

    # Build the query: products JOIN inventory_levels LEFT JOIN sales aggregate
    # Using a subquery for total_sold per product
    sold_subq = (
        select(
            Sale.product_id,
            func.sum(Sale.quantity).label("total_sold"),
        )
        .where(Sale.status == SaleStatus.COMPLETED)
        .group_by(Sale.product_id)
        .subquery()
    )

    query = (
        select(
            Product.id.label("product_id"),
            Product.sku.label("sku"),
            Product.name.label("product_name"),
            ProductCategory.name.label("category"),
            Product.unit_cost.label("unit_cost"),
            Product.selling_price.label("selling_price"),
            InventoryLevel.quantity_on_hand.label("quantity_on_hand"),
            func.coalesce(sold_subq.c.total_sold, 0).label("total_sold"),
        )
        .join(InventoryLevel, InventoryLevel.product_id == Product.id)
        .join(ProductCategory, ProductCategory.id == Product.category_id)
        .outerjoin(sold_subq, sold_subq.c.product_id == Product.id)
        .where(Product.is_active == True)  # noqa: E712
    )

    if category_id:
        query = query.where(Product.category_id == uuid.UUID(category_id))

    result = await db.execute(query)
    rows = result.all()

    items: list[StockReportItem] = []
    for row in rows:
        unit_cost = row.unit_cost or Decimal("0")
        selling_price = row.selling_price or Decimal("0")
        qty = row.quantity_on_hand or 0
        total_sold = row.total_sold or 0

        stock_value = unit_cost * Decimal(str(qty))
        potential_profit = (selling_price - unit_cost) * Decimal(str(qty))

        items.append(
            StockReportItem(
                product_id=row.product_id,
                sku=row.sku,
                product_name=row.product_name,
                category=row.category,
                unit_cost=unit_cost,
                selling_price=selling_price,
                quantity_on_hand=qty,
                stock_value=stock_value,
                potential_profit=potential_profit,
                total_sold=total_sold,
            )
        )

    total_stock_value = sum((i.stock_value for i in items), Decimal("0"))
    total_potential_profit = sum((i.potential_profit for i in items), Decimal("0"))
    total_sold_all = sum(i.total_sold for i in items)

    return StockReport(
        items=items,
        total_stock_value=total_stock_value,
        total_potential_profit=total_potential_profit,
        total_sold=total_sold_all,
    )


async def get_purchase_sale_report(
    db: AsyncSession,
    start_date: date | None = None,
    end_date: date | None = None,
) -> PurchaseSaleReport:
    """Generate a purchase and sale summary report.

    Args:
        db: Async database session.
        start_date: Start of reporting period (inclusive). None means all time.
        end_date: End of reporting period (inclusive). None means all time.

    Returns:
        PurchaseSaleReport with purchase and sales totals.
    """
    logger.info(
        "generating purchase_sale_report", start_date=start_date, end_date=end_date
    )

    # -- Total purchases --
    purchase_query = select(func.sum(PurchaseOrder.total_amount))
    if start_date:
        purchase_query = purchase_query.where(PurchaseOrder.created_at >= start_date)
    if end_date:
        purchase_query = purchase_query.where(PurchaseOrder.created_at <= end_date)
    purchase_result = await db.execute(purchase_query)
    total_purchase = purchase_result.scalar() or Decimal("0")

    # -- Purchase returns in period --
    purchase_returns_query = select(func.sum(PurchaseReturn.total_amount))
    if start_date:
        purchase_returns_query = purchase_returns_query.where(
            PurchaseReturn.return_date >= start_date
        )
    if end_date:
        purchase_returns_query = purchase_returns_query.where(
            PurchaseReturn.return_date <= end_date
        )
    purchase_returns_result = await db.execute(purchase_returns_query)
    total_purchase_returns = purchase_returns_result.scalar() or Decimal("0")

    # -- Total completed sales --
    sales_query = select(func.sum(Sale.total_amount)).where(
        Sale.status == SaleStatus.COMPLETED
    )
    if start_date:
        sales_query = sales_query.where(Sale.sale_date >= start_date)
    if end_date:
        sales_query = sales_query.where(Sale.sale_date <= end_date)
    sales_result = await db.execute(sales_query)
    total_sales = sales_result.scalar() or Decimal("0")

    # -- Sell returns in period --
    total_sales_returns = await _sum_sell_returns(db, start_date, end_date)

    net_position = total_sales - total_purchase

    return PurchaseSaleReport(
        total_purchase=total_purchase,
        total_purchase_returns=total_purchase_returns,
        total_sales=total_sales,
        total_sales_returns=total_sales_returns,
        net_position=net_position,
    )
