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
from src.core.csv_utils import csv_safe
from src.core.database import get_db
from src.reports.schemas import (
    ProductSalesReport,
    ProfitLossReport,
    PurchaseSaleReport,
    StockReport,
    TrendingProductsReport,
)
from src.reports.service import (
    get_product_sales_report,
    get_profit_loss_report,
    get_purchase_sale_report,
    get_stock_report,
    get_trending_products,
    resolve_default_date_range,
)

router = APIRouter()


# Static route BEFORE the base /profit-loss endpoint
@router.get("/profit-loss/export-csv")
async def export_profit_loss_csv(
    start_date: date | None = None,
    end_date: date | None = None,
    location_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> StreamingResponse:
    """Download the Profit & Loss report as a CSV file."""
    if start_date is None and end_date is None:
        start_date, end_date = await resolve_default_date_range(db, current_user.id)
    report = await get_profit_loss_report(
        db, start_date=start_date, end_date=end_date, location_id=location_id
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["field", "value"])
    writer.writerow(["total_purchase_excl_tax", str(report.total_purchase_excl_tax)])
    writer.writerow(["purchase_returns_total", str(report.purchase_returns_total)])
    writer.writerow(["total_sales", str(report.total_sales)])
    writer.writerow(["total_sales_returns", str(report.total_sales_returns)])
    writer.writerow(["gross_profit", str(report.gross_profit)])
    writer.writerow(["total_operating_costs", str(report.total_operating_costs)])
    writer.writerow(["net_profit", str(report.net_profit)])
    writer.writerow(["opening_stock_value", str(report.opening_stock_value)])
    writer.writerow(["closing_stock_value", str(report.closing_stock_value)])
    writer.writerow(["purchase_due", str(report.purchase_due)])
    writer.writerow(["sales_due", str(report.sales_due)])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=profit_loss_report.csv",
            "Cache-Control": "no-store, private",
        },
    )


@router.get("/profit-loss", response_model=ProfitLossReport)
async def profit_loss_endpoint(
    start_date: date | None = None,
    end_date: date | None = None,
    location_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProfitLossReport:
    """Return profit and loss report for an optional date range."""
    if start_date is None and end_date is None:
        start_date, end_date = await resolve_default_date_range(db, current_user.id)
    return await get_profit_loss_report(
        db, start_date=start_date, end_date=end_date, location_id=location_id
    )


# Static route BEFORE parameterized routes
@router.get("/stock/export-csv")
async def export_stock_csv(
    category_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> StreamingResponse:
    """Download the stock report as a CSV file."""
    report = await get_stock_report(
        db,
        category_id=str(category_id) if category_id else None,
        location_id=location_id,
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
                csv_safe(item.sku),
                csv_safe(item.product_name),
                csv_safe(item.category or ""),
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
    location_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> StockReport:
    """Return the current stock report."""
    return await get_stock_report(
        db,
        category_id=str(category_id) if category_id else None,
        location_id=location_id,
    )


# Static route BEFORE the base /purchase-sale endpoint
@router.get("/purchase-sale/export-csv")
async def export_purchase_sale_csv(
    start_date: date | None = None,
    end_date: date | None = None,
    location_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> StreamingResponse:
    """Download the Purchase & Sale report as a CSV file."""
    if start_date is None and end_date is None:
        start_date, end_date = await resolve_default_date_range(db, current_user.id)
    report = await get_purchase_sale_report(
        db, start_date=start_date, end_date=end_date, location_id=location_id
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["field", "value"])
    writer.writerow(["total_purchase", str(report.total_purchase)])
    writer.writerow(["total_purchase_returns", str(report.total_purchase_returns)])
    writer.writerow(["total_sales", str(report.total_sales)])
    writer.writerow(["total_sales_returns", str(report.total_sales_returns)])
    writer.writerow(["net_position", str(report.net_position)])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=purchase_sale_report.csv",
            "Cache-Control": "no-store, private",
        },
    )


@router.get("/purchase-sale", response_model=PurchaseSaleReport)
async def purchase_sale_endpoint(
    start_date: date | None = None,
    end_date: date | None = None,
    location_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PurchaseSaleReport:
    """Return purchase and sale summary for an optional date range."""
    if start_date is None and end_date is None:
        start_date, end_date = await resolve_default_date_range(db, current_user.id)
    return await get_purchase_sale_report(
        db, start_date=start_date, end_date=end_date, location_id=location_id
    )


@router.get("/product-sales", response_model=ProductSalesReport)
async def product_sales_endpoint(
    start_date: date | None = None,
    end_date: date | None = None,
    category_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> ProductSalesReport:
    """Return per-product sales report grouped by product."""
    return await get_product_sales_report(
        db,
        start_date=start_date,
        end_date=end_date,
        category_id=category_id,
        location_id=location_id,
        page=page,
        page_size=page_size,
    )


@router.get("/trending-products", response_model=TrendingProductsReport)
async def trending_products_endpoint(
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 10,
    sort_by: str = "revenue",
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> TrendingProductsReport:
    """Return top-N trending products sorted by revenue or quantity."""
    return await get_trending_products(
        db,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        sort_by=sort_by,
    )
