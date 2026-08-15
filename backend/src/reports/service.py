"""Reports domain business logic."""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cashflow.models import OperatingCost
from src.inventory.models import InventoryBatch
from src.inventory.service import inventory_on_hand_by_product_subquery
from src.orders.models import OrderPayment, OrderPaymentStatus, PurchaseOrder, PurchaseReturn
from src.products.models import Product, ProductCategory
from src.reports.schemas import (
    ProductSalesReport,
    ProductSalesRow,
    ProfitLossReport,
    PurchaseSaleReport,
    StockReport,
    StockReportItem,
    TrendingProductRow,
    TrendingProductsReport,
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
    location_id: uuid.UUID | None = None,
    business_id: uuid.UUID | None = None,
) -> Decimal:
    q = select(func.sum(SellReturn.total_amount))
    if location_id or business_id:
        q = q.join(Sale, Sale.id == SellReturn.sale_id)
        if location_id:
            q = q.where(Sale.location_id == location_id)
        if business_id:
            q = q.where(Sale.business_id == business_id)
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
    location_id: uuid.UUID | None = None,
    business_id: uuid.UUID | None = None,
) -> ProfitLossReport:
    """Calculate profit and loss report for an optional date range.

    Args:
        db: Async database session.
        start_date: Start of reporting period (inclusive). None means all time.
        end_date: End of reporting period (inclusive). None means all time.
        business_id: Restrict report to this business's data.

    Returns:
        ProfitLossReport with all computed fields.
    """
    logger.info(
        "generating profit_loss_report", start_date=start_date, end_date=end_date,
        business_id=business_id,
    )

    # -- Total purchases (sum of all purchase orders in period) --
    # order_date, not created_at — order_date is when the purchase actually
    # happened (matches sales_query's use of Sale.sale_date below, and
    # dashboard/service.py's identical purchase query); created_at is only
    # when the row was inserted into ModishLog, which for a backdated order
    # (an import, or any manually-entered historical purchase) silently
    # excludes it from date-scoped reports entirely.
    purchase_query = select(func.sum(PurchaseOrder.total_amount))
    if business_id:
        purchase_query = purchase_query.where(PurchaseOrder.business_id == business_id)
    if start_date:
        purchase_query = purchase_query.where(PurchaseOrder.order_date >= start_date)
    if end_date:
        purchase_query = purchase_query.where(PurchaseOrder.order_date <= end_date)
    if location_id:
        purchase_query = purchase_query.where(PurchaseOrder.location_id == location_id)
    purchase_result = await db.execute(purchase_query)
    total_purchase = purchase_result.scalar() or Decimal("0")

    # -- Total completed sales in period --
    sales_query = select(func.sum(Sale.total_amount)).where(
        Sale.status == SaleStatus.COMPLETED
    )
    if business_id:
        sales_query = sales_query.where(Sale.business_id == business_id)
    if start_date:
        sales_query = sales_query.where(Sale.sale_date >= start_date)
    if end_date:
        sales_query = sales_query.where(Sale.sale_date <= end_date)
    if location_id:
        sales_query = sales_query.where(Sale.location_id == location_id)
    sales_result = await db.execute(sales_query)
    total_sales = sales_result.scalar() or Decimal("0")

    # -- Operating costs (active only, scoped to business) --
    opex_query = select(OperatingCost).where(OperatingCost.is_active == True)  # noqa: E712
    if business_id:
        opex_query = opex_query.where(OperatingCost.business_id == business_id)
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
    # InventoryBatch has no business_id column of its own -- scoped through
    # a join to Product. Without this, every business's opening/closing
    # stock value is actually the total landed-cost inventory value of
    # every product from every tenant in the database (task 208).
    stock_query = select(
        func.sum(
            InventoryBatch.quantity_remaining * InventoryBatch.landed_cost_per_unit
        )
    )
    if business_id:
        stock_query = stock_query.join(
            Product, Product.id == InventoryBatch.product_id
        ).where(Product.business_id == business_id)
    stock_result = await db.execute(stock_query)
    stock_value = stock_result.scalar() or Decimal("0")

    # -- Purchase returns in period --
    returns_query = select(func.sum(PurchaseReturn.total_amount))
    if location_id or business_id:
        returns_query = returns_query.join(
            PurchaseOrder, PurchaseOrder.id == PurchaseReturn.original_order_id
        )
        if location_id:
            returns_query = returns_query.where(PurchaseOrder.location_id == location_id)
        if business_id:
            returns_query = returns_query.where(PurchaseOrder.business_id == business_id)
    if start_date:
        returns_query = returns_query.where(PurchaseReturn.return_date >= start_date)
    if end_date:
        returns_query = returns_query.where(PurchaseReturn.return_date <= end_date)
    returns_result = await db.execute(returns_query)
    purchase_returns_total = returns_result.scalar() or Decimal("0")

    # -- Sell returns in period --
    total_sales_returns = await _sum_sell_returns(
        db, start_date, end_date, location_id, business_id
    )

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
    if business_id:
        purchase_due_query = purchase_due_query.where(
            PurchaseOrder.business_id == business_id
        )
    if start_date:
        purchase_due_query = purchase_due_query.where(PurchaseOrder.order_date >= start_date)
    if end_date:
        purchase_due_query = purchase_due_query.where(PurchaseOrder.order_date <= end_date)
    if location_id:
        purchase_due_query = purchase_due_query.where(PurchaseOrder.location_id == location_id)
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
        .where(
            or_(
                Sale.payment_status.is_(None),
                Sale.payment_status != "paid",
            )
        )
    )
    if business_id:
        sales_due_query = sales_due_query.where(Sale.business_id == business_id)
    if start_date:
        sales_due_query = sales_due_query.where(Sale.sale_date >= start_date)
    if end_date:
        sales_due_query = sales_due_query.where(Sale.sale_date <= end_date)
    if location_id:
        sales_due_query = sales_due_query.where(Sale.location_id == location_id)
    sales_due_result = await db.execute(sales_due_query)
    sales_due = sales_due_result.scalar() or Decimal("0")

    gross_profit = total_sales - total_sales_returns - total_purchase
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
    location_id: uuid.UUID | None = None,
    business_id: uuid.UUID | None = None,
) -> StockReport:
    """Generate a stock report showing inventory levels and valuations.

    Args:
        db: Async database session.
        category_id: Optional UUID string to filter by product category.
        business_id: Restrict report to this business's data.

    Returns:
        StockReport with per-product rows and aggregated totals.
    """
    logger.info("generating stock_report", category_id=category_id, business_id=business_id)

    # Build the query: products JOIN inventory_levels LEFT JOIN sales aggregate
    # Using a subquery for total_sold per product
    sold_subq_base = select(
        Sale.product_id,
        func.sum(Sale.quantity).label("total_sold"),
    ).where(Sale.status == SaleStatus.COMPLETED)
    if location_id:
        sold_subq_base = sold_subq_base.where(Sale.location_id == location_id)
    if business_id:
        sold_subq_base = sold_subq_base.where(Sale.business_id == business_id)
    sold_subq = sold_subq_base.group_by(Sale.product_id).subquery()

    inventory_subq = inventory_on_hand_by_product_subquery()

    query = (
        select(
            Product.id.label("product_id"),
            Product.sku.label("sku"),
            Product.name.label("product_name"),
            ProductCategory.name.label("category"),
            Product.unit_cost.label("unit_cost"),
            Product.selling_price.label("selling_price"),
            inventory_subq.c.quantity_on_hand.label("quantity_on_hand"),
            func.coalesce(sold_subq.c.total_sold, 0).label("total_sold"),
        )
        .join(inventory_subq, inventory_subq.c.product_id == Product.id)
        .join(ProductCategory, ProductCategory.id == Product.category_id)
        .outerjoin(sold_subq, sold_subq.c.product_id == Product.id)
        .where(Product.is_active == True)  # noqa: E712
    )

    if category_id:
        query = query.where(Product.category_id == uuid.UUID(category_id))
    if business_id:
        # Without this, the main product query returns every active
        # product from every business, including unit_cost/selling_price
        # -- total_sold stays correctly scoped via sold_subq_base above,
        # but the product rows themselves were not (task 208).
        query = query.where(Product.business_id == business_id)

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
    location_id: uuid.UUID | None = None,
    business_id: uuid.UUID | None = None,
) -> PurchaseSaleReport:
    """Generate a purchase and sale summary report.

    Args:
        db: Async database session.
        start_date: Start of reporting period (inclusive). None means all time.
        end_date: End of reporting period (inclusive). None means all time.
        business_id: Restrict report to this business's data.

    Returns:
        PurchaseSaleReport with purchase and sales totals.
    """
    logger.info(
        "generating purchase_sale_report", start_date=start_date, end_date=end_date,
        business_id=business_id,
    )

    # -- Total purchases --
    # order_date, not created_at — same fix and rationale as
    # get_profit_loss_report()'s identical purchase query above.
    purchase_query = select(func.sum(PurchaseOrder.total_amount))
    if business_id:
        purchase_query = purchase_query.where(PurchaseOrder.business_id == business_id)
    if start_date:
        purchase_query = purchase_query.where(PurchaseOrder.order_date >= start_date)
    if end_date:
        purchase_query = purchase_query.where(PurchaseOrder.order_date <= end_date)
    if location_id:
        purchase_query = purchase_query.where(PurchaseOrder.location_id == location_id)
    purchase_result = await db.execute(purchase_query)
    total_purchase = purchase_result.scalar() or Decimal("0")

    # -- Purchase returns in period --
    purchase_returns_query = select(func.sum(PurchaseReturn.total_amount))
    if business_id:
        purchase_returns_query = purchase_returns_query.join(
            PurchaseOrder, PurchaseOrder.id == PurchaseReturn.original_order_id
        ).where(PurchaseOrder.business_id == business_id)
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
    if business_id:
        sales_query = sales_query.where(Sale.business_id == business_id)
    if start_date:
        sales_query = sales_query.where(Sale.sale_date >= start_date)
    if end_date:
        sales_query = sales_query.where(Sale.sale_date <= end_date)
    if location_id:
        sales_query = sales_query.where(Sale.location_id == location_id)
    sales_result = await db.execute(sales_query)
    total_sales = sales_result.scalar() or Decimal("0")

    # -- Sell returns in period --
    total_sales_returns = await _sum_sell_returns(
        db, start_date, end_date, business_id=business_id
    )

    net_position = total_sales - total_purchase

    return PurchaseSaleReport(
        total_purchase=total_purchase,
        total_purchase_returns=total_purchase_returns,
        total_sales=total_sales,
        total_sales_returns=total_sales_returns,
        net_position=net_position,
    )


async def get_product_sales_report(
    db: AsyncSession,
    start_date: date | None = None,
    end_date: date | None = None,
    category_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    business_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 20,
) -> ProductSalesReport:
    """Group completed sales by product for the given period."""
    logger.info(
        "generating product_sales_report",
        start_date=start_date,
        end_date=end_date,
        page=page,
        business_id=business_id,
    )

    # Returns subquery: count of sell_returns per product (via sale join)
    returns_subq = (
        select(
            Sale.product_id.label("product_id"),
            func.count(SellReturn.id).label("return_quantity"),
        )
        .join(SellReturn, SellReturn.sale_id == Sale.id)
        .group_by(Sale.product_id)
        .subquery()
    )

    base_q = (
        select(
            Product.id.label("product_id"),
            Product.sku.label("sku"),
            Product.name.label("product_name"),
            ProductCategory.name.label("category"),
            func.sum(Sale.quantity).label("quantity_sold"),
            func.sum(Sale.total_amount).label("total_revenue"),
            func.coalesce(
                func.sum(Sale.total_amount) / func.nullif(func.sum(Sale.quantity), 0),
                Decimal("0"),
            ).label("avg_unit_price"),
            func.coalesce(returns_subq.c.return_quantity, 0).label("return_quantity"),
        )
        .join(Sale, Sale.product_id == Product.id)
        .join(ProductCategory, ProductCategory.id == Product.category_id)
        .outerjoin(returns_subq, returns_subq.c.product_id == Product.id)
        .where(Sale.status == SaleStatus.COMPLETED)
        .group_by(
            Product.id,
            Product.sku,
            Product.name,
            ProductCategory.name,
        )
    )

    if business_id:
        base_q = base_q.where(Sale.business_id == business_id)
    if start_date:
        base_q = base_q.where(Sale.sale_date >= start_date)
    if end_date:
        base_q = base_q.where(Sale.sale_date <= end_date)
    if category_id:
        base_q = base_q.where(Product.category_id == category_id)
    if location_id:
        base_q = base_q.where(Sale.location_id == location_id)

    # Total count and global revenue (both wrap base_q as subquery)
    count_subq = base_q.subquery()
    count_result = await db.execute(
        select(func.count()).select_from(count_subq)
    )
    total = count_result.scalar() or 0

    # Global revenue across ALL matching products (not just this page)
    revenue_subq = base_q.subquery()
    revenue_result = await db.execute(
        select(func.sum(revenue_subq.c.total_revenue)).select_from(revenue_subq)
    )
    total_revenue = revenue_result.scalar() or Decimal("0")

    # Paginate
    paginated_q = base_q.offset((page - 1) * page_size).limit(page_size)
    rows_result = await db.execute(paginated_q)
    rows_data = rows_result.all()

    rows: list[ProductSalesRow] = []
    for r in rows_data:
        qty_sold = r.quantity_sold or 0
        ret_qty = r.return_quantity or 0
        rows.append(
            ProductSalesRow(
                product_id=r.product_id,
                sku=r.sku,
                product_name=r.product_name,
                category=r.category,
                quantity_sold=qty_sold,
                total_revenue=r.total_revenue or Decimal("0"),
                avg_unit_price=r.avg_unit_price or Decimal("0"),
                return_quantity=ret_qty,
                net_quantity=qty_sold - ret_qty,
            )
        )

    return ProductSalesReport(
        rows=rows,
        total_revenue=total_revenue,
        period_start=start_date,
        period_end=end_date,
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_trending_products(
    db: AsyncSession,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 10,
    sort_by: Literal["revenue", "quantity"] = "revenue",
    business_id: uuid.UUID | None = None,
) -> TrendingProductsReport:
    """Return top-N products sorted by revenue or quantity."""
    logger.info(
        "generating trending_products",
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        sort_by=sort_by,
        business_id=business_id,
    )

    order_col = (
        func.sum(Sale.total_amount).desc()
        if sort_by == "revenue"
        else func.sum(Sale.quantity).desc()
    )

    q = (
        select(
            Product.id.label("product_id"),
            Product.sku.label("sku"),
            Product.name.label("product_name"),
            ProductCategory.name.label("category"),
            func.sum(Sale.quantity).label("quantity_sold"),
            func.sum(Sale.total_amount).label("total_revenue"),
        )
        .join(Sale, Sale.product_id == Product.id)
        .join(ProductCategory, ProductCategory.id == Product.category_id)
        .where(Sale.status == SaleStatus.COMPLETED)
        .group_by(Product.id, Product.sku, Product.name, ProductCategory.name)
    )

    if business_id:
        q = q.where(Sale.business_id == business_id)
    if start_date:
        q = q.where(Sale.sale_date >= start_date)
    if end_date:
        q = q.where(Sale.sale_date <= end_date)

    q = q.order_by(order_col).limit(limit)

    result = await db.execute(q)
    rows_data = result.all()

    rows = [
        TrendingProductRow(
            rank=i + 1,
            product_id=r.product_id,
            product_name=r.product_name,
            sku=r.sku,
            category=r.category,
            quantity_sold=r.quantity_sold or 0,
            total_revenue=r.total_revenue or Decimal("0"),
        )
        for i, r in enumerate(rows_data)
    ]

    return TrendingProductsReport(
        rows=rows,
        period_start=start_date,
        period_end=end_date,
    )
