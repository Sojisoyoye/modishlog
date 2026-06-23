"""Dashboard domain — KPI summary aggregation service."""

import asyncio
import uuid
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cashflow.models import OperatingCost
from src.dashboard.schemas import DashboardSummaryResponse
from src.locations.models import BusinessLocation
from src.orders.models import OrderPaymentStatus, PurchaseOrder, PurchaseReturn
from src.sales.models import Sale, SaleStatus, SellReturn


_ZERO = Decimal("0")


async def get_dashboard_summary(
    db: AsyncSession,
    user_id: uuid.UUID,
    location_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> DashboardSummaryResponse:
    """Aggregate all 10 KPI values for the dashboard summary."""

    # -- Location ownership guard -----------------------------------------
    if location_id is not None:
        owned = await db.scalar(
            select(BusinessLocation.id).where(
                BusinessLocation.id == location_id,
                BusinessLocation.created_by == user_id,
            )
        )
        if owned is None:
            raise HTTPException(status_code=404, detail="Location not found")

    # -- Build all queries ------------------------------------------------
    q = select(func.coalesce(func.sum(Sale.total_amount), _ZERO)).where(
        Sale.recorded_by == user_id,
        Sale.status == SaleStatus.COMPLETED,
    )
    if location_id:
        q = q.where(Sale.location_id == location_id)
    if date_from:
        q = q.where(Sale.sale_date >= date_from)
    if date_to:
        q = q.where(Sale.sale_date <= date_to)

    q_cogs = select(func.coalesce(func.sum(Sale.fifo_cogs), _ZERO)).where(
        Sale.recorded_by == user_id,
        Sale.status == SaleStatus.COMPLETED,
        Sale.fifo_cogs.isnot(None),
    )
    if location_id:
        q_cogs = q_cogs.where(Sale.location_id == location_id)
    if date_from:
        q_cogs = q_cogs.where(Sale.sale_date >= date_from)
    if date_to:
        q_cogs = q_cogs.where(Sale.sale_date <= date_to)

    # OperatingCost stores a normalised monthly rate; pro-rate when a
    # bounded date range is given to avoid over-subtracting from net.
    q_exp = select(
        func.coalesce(func.sum(OperatingCost.monthly_equivalent), _ZERO)
    ).where(
        OperatingCost.created_by == user_id,
        OperatingCost.is_active.is_(True),
    )

    q_inv = select(func.coalesce(func.sum(Sale.total_amount), _ZERO)).where(
        Sale.recorded_by == user_id,
        Sale.status == SaleStatus.COMPLETED,
        or_(Sale.payment_status.is_(None), Sale.payment_status != "paid"),
    )
    if location_id:
        q_inv = q_inv.where(Sale.location_id == location_id)
    if date_from:
        q_inv = q_inv.where(Sale.sale_date >= date_from)
    if date_to:
        q_inv = q_inv.where(Sale.sale_date <= date_to)

    # Merged sell-return query: both sums in one JOIN to halve the DB work.
    q_sr = select(
        func.coalesce(func.sum(SellReturn.total_amount), _ZERO),
        func.coalesce(func.sum(SellReturn.amount_paid), _ZERO),
    ).join(Sale, SellReturn.sale_id == Sale.id).where(
        Sale.recorded_by == user_id,
        Sale.status == SaleStatus.COMPLETED,
    )
    if location_id:
        q_sr = q_sr.where(Sale.location_id == location_id)
    if date_from:
        q_sr = q_sr.where(SellReturn.return_date >= date_from)
    if date_to:
        q_sr = q_sr.where(SellReturn.return_date <= date_to)

    q_po = select(func.coalesce(func.sum(PurchaseOrder.total_amount), _ZERO)).where(
        PurchaseOrder.created_by == user_id,
    )
    if location_id:
        q_po = q_po.where(PurchaseOrder.location_id == location_id)
    if date_from:
        q_po = q_po.where(PurchaseOrder.order_date >= date_from)
    if date_to:
        q_po = q_po.where(PurchaseOrder.order_date <= date_to)

    q_pd = select(func.coalesce(func.sum(PurchaseOrder.total_amount), _ZERO)).where(
        PurchaseOrder.created_by == user_id,
        PurchaseOrder.payment_status == OrderPaymentStatus.UNPAID,
    )
    if location_id:
        q_pd = q_pd.where(PurchaseOrder.location_id == location_id)
    if date_from:
        q_pd = q_pd.where(PurchaseOrder.order_date >= date_from)
    if date_to:
        q_pd = q_pd.where(PurchaseOrder.order_date <= date_to)

    q_pr = select(
        func.coalesce(func.sum(PurchaseReturn.total_amount), _ZERO)
    ).join(
        PurchaseOrder, PurchaseReturn.original_order_id == PurchaseOrder.id
    ).where(PurchaseOrder.created_by == user_id)
    if date_from:
        q_pr = q_pr.where(PurchaseReturn.return_date >= date_from)
    if date_to:
        q_pr = q_pr.where(PurchaseReturn.return_date <= date_to)

    # -- Execute all queries concurrently (asyncpg pipelines them) --------
    r_sales, r_cogs, r_expense, r_inv, r_sr, r_po, r_pd, r_pr = await asyncio.gather(
        db.execute(q),
        db.execute(q_cogs),
        db.execute(q_exp),
        db.execute(q_inv),
        db.execute(q_sr),
        db.execute(q_po),
        db.execute(q_pd),
        db.execute(q_pr),
    )

    total_sales: Decimal = r_sales.scalar_one()
    total_cogs: Decimal = r_cogs.scalar_one()
    raw_monthly_expense: Decimal = r_expense.scalar_one()
    invoice_due: Decimal = r_inv.scalar_one()

    sr_row = r_sr.one()
    total_sell_return: Decimal = sr_row[0]
    total_sell_return_paid: Decimal = sr_row[1]

    total_purchase: Decimal = r_po.scalar_one()
    purchase_due: Decimal = r_pd.scalar_one()
    total_purchase_return: Decimal = r_pr.scalar_one()

    # -- Derived values ---------------------------------------------------
    if date_from and date_to:
        range_days = Decimal((date_to - date_from).days + 1)
        expense = raw_monthly_expense * range_days / Decimal(30)
    else:
        expense = raw_monthly_expense

    net = total_sales - total_cogs - expense
    total_purchase_return_paid = total_purchase_return

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
    )
