"""Dashboard domain — KPI summary aggregation service."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cashflow.models import OperatingCost
from src.dashboard.schemas import DashboardSummaryResponse, RecentSaleItem
from src.orders.models import (
    OrderPayment,
    OrderPaymentStatus,
    PaymentStatus,
    PurchaseOrder,
    PurchaseReturn,
)
from src.products.models import Product
from src.sales.models import Sale, SaleStatus, SellReturn


_ZERO = Decimal("0")


async def get_dashboard_summary(
    db: AsyncSession,
    business_id: uuid.UUID,
    location_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> DashboardSummaryResponse:
    """Aggregate all 10 KPI values for the dashboard summary."""

    # -- Build all queries ------------------------------------------------
    q = select(func.coalesce(func.sum(Sale.total_amount), _ZERO)).where(
        Sale.business_id == business_id,
        Sale.status == SaleStatus.COMPLETED,
    )
    if location_id is not None:
        q = q.where(Sale.location_id == location_id)
    if date_from is not None:
        q = q.where(Sale.sale_date >= date_from)
    if date_to is not None:
        q = q.where(Sale.sale_date <= date_to)

    q_cogs = select(func.coalesce(func.sum(Sale.fifo_cogs), _ZERO)).where(
        Sale.business_id == business_id,
        Sale.status == SaleStatus.COMPLETED,
        Sale.fifo_cogs.isnot(None),
    )
    if location_id is not None:
        q_cogs = q_cogs.where(Sale.location_id == location_id)
    if date_from is not None:
        q_cogs = q_cogs.where(Sale.sale_date >= date_from)
    if date_to is not None:
        q_cogs = q_cogs.where(Sale.sale_date <= date_to)

    # OperatingCost stores a normalised monthly rate; pro-rate when a bounded
    # date range is given to avoid over-subtracting from net.
    # NOTE: OperatingCost has no location_id column, so this aggregation is
    # always business-scope regardless of the location filter.
    q_exp = select(
        func.coalesce(func.sum(OperatingCost.monthly_equivalent), _ZERO)
    ).where(
        OperatingCost.business_id == business_id,
        OperatingCost.is_active.is_(True),
    )

    q_inv = select(func.coalesce(func.sum(Sale.total_amount), _ZERO)).where(
        Sale.business_id == business_id,
        Sale.status == SaleStatus.COMPLETED,
        or_(Sale.payment_status.is_(None), Sale.payment_status != "paid"),
    )
    if location_id is not None:
        q_inv = q_inv.where(Sale.location_id == location_id)
    if date_from is not None:
        q_inv = q_inv.where(Sale.sale_date >= date_from)
    if date_to is not None:
        q_inv = q_inv.where(Sale.sale_date <= date_to)

    # Merged sell-return query: both sums in one JOIN to halve the DB work.
    q_sr = (
        select(
            func.coalesce(func.sum(SellReturn.total_amount), _ZERO),
            func.coalesce(func.sum(SellReturn.amount_paid), _ZERO),
        )
        .join(Sale, SellReturn.sale_id == Sale.id)
        .where(
            Sale.business_id == business_id,
            Sale.status == SaleStatus.COMPLETED,
        )
    )
    if location_id is not None:
        q_sr = q_sr.where(Sale.location_id == location_id)
    if date_from is not None:
        q_sr = q_sr.where(SellReturn.return_date >= date_from)
    if date_to is not None:
        q_sr = q_sr.where(SellReturn.return_date <= date_to)

    q_po = select(func.coalesce(func.sum(PurchaseOrder.total_amount), _ZERO)).where(
        PurchaseOrder.business_id == business_id,
    )
    if location_id is not None:
        q_po = q_po.where(PurchaseOrder.location_id == location_id)
    if date_from is not None:
        q_po = q_po.where(PurchaseOrder.order_date >= date_from)
    if date_to is not None:
        q_po = q_po.where(PurchaseOrder.order_date <= date_to)

    # purchase_due = remaining balance per order (total_amount − completed payments).
    # UNPAID orders have no payments so full total_amount is due.
    # PARTIAL orders have some payments; only the remainder is outstanding.
    _paid_subq = (
        select(
            OrderPayment.order_id.label("order_id"),
            func.coalesce(func.sum(OrderPayment.amount), _ZERO).label("paid"),
        )
        .where(OrderPayment.status == PaymentStatus.COMPLETED)
        .group_by(OrderPayment.order_id)
        .subquery()
    )
    q_pd = (
        select(
            func.coalesce(
                func.sum(
                    PurchaseOrder.total_amount - func.coalesce(_paid_subq.c.paid, _ZERO)
                ),
                _ZERO,
            )
        )
        .outerjoin(_paid_subq, _paid_subq.c.order_id == PurchaseOrder.id)
        .where(
            PurchaseOrder.business_id == business_id,
            PurchaseOrder.payment_status.in_(
                [OrderPaymentStatus.UNPAID, OrderPaymentStatus.PARTIAL]
            ),
        )
    )
    if location_id is not None:
        q_pd = q_pd.where(PurchaseOrder.location_id == location_id)
    if date_from is not None:
        q_pd = q_pd.where(PurchaseOrder.order_date >= date_from)
    if date_to is not None:
        q_pd = q_pd.where(PurchaseOrder.order_date <= date_to)

    # Fetch both total_amount and amount_paid in one pass through the join.
    q_pr = (
        select(
            func.coalesce(func.sum(PurchaseReturn.total_amount), _ZERO),
            func.coalesce(func.sum(PurchaseReturn.amount_paid), _ZERO),
        )
        .join(PurchaseOrder, PurchaseReturn.original_order_id == PurchaseOrder.id)
        .where(PurchaseOrder.business_id == business_id)
    )
    if location_id is not None:
        q_pr = q_pr.where(PurchaseOrder.location_id == location_id)
    if date_from is not None:
        q_pr = q_pr.where(PurchaseReturn.return_date >= date_from)
    if date_to is not None:
        q_pr = q_pr.where(PurchaseReturn.return_date <= date_to)

    # -- transaction count for the selected period -------------------------
    q_count = select(func.count(Sale.id)).where(
        Sale.business_id == business_id,
        Sale.status == SaleStatus.COMPLETED,
    )
    if location_id is not None:
        q_count = q_count.where(Sale.location_id == location_id)
    if date_from is not None:
        q_count = q_count.where(Sale.sale_date >= date_from)
    if date_to is not None:
        q_count = q_count.where(Sale.sale_date <= date_to)

    # -- yesterday's revenue (always calendar yesterday, same location) ----
    _yesterday = date.today() - timedelta(days=1)
    q_yesterday = select(func.coalesce(func.sum(Sale.total_amount), _ZERO)).where(
        Sale.business_id == business_id,
        Sale.status == SaleStatus.COMPLETED,
        Sale.sale_date == _yesterday,
    )
    if location_id is not None:
        q_yesterday = q_yesterday.where(Sale.location_id == location_id)

    # -- last 5 recent sales with product name ----------------------------
    q_recent = (
        select(Product.name, Sale.quantity, Sale.total_amount, Sale.fifo_cogs)
        .join(Product, Sale.product_id == Product.id)
        .where(
            Sale.business_id == business_id,
            Sale.status == SaleStatus.COMPLETED,
        )
        .order_by(Sale.created_at.desc())
        .limit(5)
    )
    if location_id is not None:
        q_recent = q_recent.where(Sale.location_id == location_id)
    if date_from is not None:
        q_recent = q_recent.where(Sale.sale_date >= date_from)
    if date_to is not None:
        q_recent = q_recent.where(Sale.sale_date <= date_to)

    # -- Execute queries sequentially on the shared AsyncSession ----------
    # AsyncSession is not safe for concurrent use across multiple coroutines;
    # run each query in turn rather than via asyncio.gather.
    r_sales = await db.execute(q)
    r_cogs = await db.execute(q_cogs)
    r_expense = await db.execute(q_exp)
    r_inv = await db.execute(q_inv)
    r_sr = await db.execute(q_sr)
    r_po = await db.execute(q_po)
    r_pd = await db.execute(q_pd)
    r_pr = await db.execute(q_pr)
    r_count = await db.execute(q_count)
    r_yesterday = await db.execute(q_yesterday)
    r_recent = await db.execute(q_recent)

    total_sales: Decimal = r_sales.scalar_one()
    total_cogs: Decimal = r_cogs.scalar_one()
    raw_monthly_expense: Decimal = r_expense.scalar_one()
    invoice_due: Decimal = r_inv.scalar_one()

    sr_row = r_sr.one()
    total_sell_return: Decimal = sr_row[0]
    total_sell_return_paid: Decimal = sr_row[1]

    total_purchase: Decimal = r_po.scalar_one()
    purchase_due: Decimal = r_pd.scalar_one()

    pr_row = r_pr.one()
    total_purchase_return: Decimal = pr_row[0]
    total_purchase_return_paid: Decimal = pr_row[1]

    transaction_count: int = r_count.scalar_one()
    yesterday_sales: Decimal = r_yesterday.scalar_one()
    recent_rows = r_recent.all()

    def _margin_str(revenue: Decimal, cogs: Decimal | None) -> str | None:
        if cogs is None or revenue == _ZERO:
            return None
        return f"{((revenue - cogs) / revenue * 100):.1f}"

    recent_sales = [
        RecentSaleItem(
            product_name=row[0],
            quantity=row[1],
            revenue=f"{row[2]:.2f}",
            margin_pct=_margin_str(row[2], row[3]),
        )
        for row in recent_rows
    ]

    # -- Derived values ---------------------------------------------------
    if date_from and date_to:
        range_days = Decimal((date_to - date_from).days + 1)
        expense = raw_monthly_expense * range_days / Decimal(30)
    else:
        expense = raw_monthly_expense

    net = total_sales - total_cogs - expense

    return DashboardSummaryResponse(
        total_sales=total_sales,
        net=net,
        invoice_due=invoice_due,
        total_sell_return=total_sell_return,
        total_sell_return_paid=total_sell_return_paid,
        total_purchase=total_purchase,
        purchase_due=purchase_due,
        total_purchase_return=total_purchase_return,
        total_purchase_return_paid=total_purchase_return_paid,
        expense=expense,
        transaction_count=transaction_count,
        yesterday_sales=yesterday_sales,
        recent_sales=recent_sales,
    )
