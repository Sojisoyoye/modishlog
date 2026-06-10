"""Reports API routes."""

import csv
import io
import uuid
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.core.database import get_db
from src.reports.schemas import ProfitLossReport, PurchaseSaleReport, StockReport
from src.reports.service import (
    get_profit_loss_report,
    get_purchase_sale_report,
    get_stock_report,
)

router = APIRouter()


@router.get("/profit-loss", response_model=ProfitLossReport)
async def profit_loss_endpoint(
    start_date: date | None = None,
    end_date: date | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> ProfitLossReport:
    """Return profit and loss report for an optional date range."""
    return await get_profit_loss_report(db, start_date=start_date, end_date=end_date)


# Static route BEFORE parameterized routes
@router.get("/stock/export-csv")
async def export_stock_csv(
    category_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> StreamingResponse:
    """Download the stock report as a CSV file."""
    report = await get_stock_report(
        db, category_id=str(category_id) if category_id else None
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "product_id",
            "sku",
            "product_name",
            "category",
            "unit_cost",
            "selling_price",
            "quantity_on_hand",
            "stock_value",
            "potential_profit",
            "total_sold",
        ]
    )
    for item in report.items:
        writer.writerow(
            [
                str(item.product_id),
                item.sku,
                item.product_name,
                item.category or "",
                str(item.unit_cost),
                str(item.selling_price),
                item.quantity_on_hand,
                str(item.stock_value),
                str(item.potential_profit),
                item.total_sold,
            ]
        )
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=stock_report.csv"},
    )


@router.get("/stock", response_model=StockReport)
async def stock_report_endpoint(
    category_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> StockReport:
    """Return the current stock report."""
    return await get_stock_report(
        db, category_id=str(category_id) if category_id else None
    )


@router.get("/purchase-sale", response_model=PurchaseSaleReport)
async def purchase_sale_endpoint(
    start_date: date | None = None,
    end_date: date | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> PurchaseSaleReport:
    """Return purchase and sale summary for an optional date range."""
    return await get_purchase_sale_report(db, start_date=start_date, end_date=end_date)
