"""Dashboard domain — KPI summary aggregation service."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cashflow.models import OperatingCost
from src.dashboard.schemas import DashboardSummaryResponse
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

    # -- Total Sales (completed) ------------------------------------------
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
    total_sales: Decimal = (await db.execute(q)).scalar_one()

    # -- COGS (sum of fifo_cogs on completed sales) ------------------------
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
    total_cogs: Decimal = (await db.execute(q_cogs)).scalar_one()

    # -- Expense (active operating costs created by this user) -------------
    # OperatingCost stores a normalised monthly rate. When a bounded date
    # range is given we pro-rate to avoid over-subtracting from net.
    q_exp = select(
        func.coalesce(func.sum(OperatingCost.monthly_equivalent), _ZERO)
    ).where(
        OperatingCost.created_by == user_id,
        OperatingCost.is_active.is_(True),
    )
    raw_monthly_expense: Decimal = (await db.execute(q_exp)).scalar_one()
    if date_from and date_to:
        range_days = Decimal((date_to - date_from).days + 1)
        expense = raw_monthly_expense * range_days / Decimal(30)
    else:
        expense = raw_monthly_expense

    net = total_sales - total_cogs - expense

    # -- Invoice Due (sales with payment_status != 'paid') -----------------
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
    invoice_due: Decimal = (await db.execute(q_inv)).scalar_one()

    # -- Sell Return -------------------------------------------------------
    # Join SellReturn → Sale to scope by user, location, and status.
    q_sr = select(func.coalesce(func.sum(SellReturn.total_amount), _ZERO)).join(
        Sale, SellReturn.sale_id == Sale.id
    ).where(
        Sale.recorded_by == user_id,
        Sale.status == SaleStatus.COMPLETED,
    )
    if location_id:
        q_sr = q_sr.where(Sale.location_id == location_id)
    if date_from:
        q_sr = q_sr.where(SellReturn.return_date >= date_from)
    if date_to:
        q_sr = q_sr.where(SellReturn.return_date <= date_to)
    total_sell_return: Decimal = (await db.execute(q_sr)).scalar_one()

    q_srp = select(func.coalesce(func.sum(SellReturn.amount_paid), _ZERO)).join(
        Sale, SellReturn.sale_id == Sale.id
    ).where(
        Sale.recorded_by == user_id,
        Sale.status == SaleStatus.COMPLETED,
    )
    if location_id:
        q_srp = q_srp.where(Sale.location_id == location_id)
    if date_from:
        q_srp = q_srp.where(SellReturn.return_date >= date_from)
    if date_to:
        q_srp = q_srp.where(SellReturn.return_date <= date_to)
    total_sell_return_paid: Decimal = (await db.execute(q_srp)).scalar_one()

    # -- Total Purchase ----------------------------------------------------
    q_po = select(func.coalesce(func.sum(PurchaseOrder.total_amount), _ZERO)).where(
        PurchaseOrder.created_by == user_id,
    )
    if location_id:
        q_po = q_po.where(PurchaseOrder.location_id == location_id)
    if date_from:
        q_po = q_po.where(PurchaseOrder.order_date >= date_from)
    if date_to:
        q_po = q_po.where(PurchaseOrder.order_date <= date_to)
    total_purchase: Decimal = (await db.execute(q_po)).scalar_one()

    # -- Purchase Due ------------------------------------------------------
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
    purchase_due: Decimal = (await db.execute(q_pd)).scalar_one()

    # -- Purchase Return ---------------------------------------------------
    # Join PurchaseReturn → PurchaseOrder to scope by user
    q_pr = select(
        func.coalesce(func.sum(PurchaseReturn.total_amount), _ZERO)
    ).join(
        PurchaseOrder, PurchaseReturn.original_order_id == PurchaseOrder.id
    ).where(PurchaseOrder.created_by == user_id)
    if date_from:
        q_pr = q_pr.where(PurchaseReturn.return_date >= date_from)
    if date_to:
        q_pr = q_pr.where(PurchaseReturn.return_date <= date_to)
    total_purchase_return: Decimal = (await db.execute(q_pr)).scalar_one()

    # PurchaseReturn has no amount_paid; treat full amount as paid
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
