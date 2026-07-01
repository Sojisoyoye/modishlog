"""Reports domain Pydantic schemas."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ProfitLossReport(BaseModel):
    """Profit and loss summary for a given period."""

    model_config = ConfigDict(from_attributes=True)

    total_purchase_excl_tax: Decimal
    purchase_returns_total: Decimal
    total_sales: Decimal
    gross_profit: Decimal  # total_sales - total_purchase_excl_tax
    total_operating_costs: (
        Decimal  # sum of monthly_equivalent from cashflow.operating_costs
    )
    net_profit: Decimal  # gross_profit - total_operating_costs
    opening_stock_value: (
        Decimal  # sum(batches.quantity_remaining * batches.landed_cost_per_unit)
    )
    closing_stock_value: Decimal  # same at query time (current)
    total_sales_returns: Decimal  # sum of SellReturn.total_amount in period
    purchase_due: Decimal  # sum of unpaid/partial order balances
    sales_due: Decimal  # sum of (total_amount - payment_amount) for credit/partial sales


class StockReportItem(BaseModel):
    """Individual product row in a stock report."""

    model_config = ConfigDict(from_attributes=True)

    product_id: uuid.UUID
    sku: str
    product_name: str
    category: str | None
    unit_cost: Decimal
    selling_price: Decimal
    quantity_on_hand: int
    stock_value: Decimal  # qty * unit_cost
    potential_profit: Decimal  # (selling_price - unit_cost) * qty
    total_sold: int  # sum of sales qty for this product


class StockReport(BaseModel):
    """Stock report with aggregated totals."""

    model_config = ConfigDict(from_attributes=True)

    items: list[StockReportItem]
    total_stock_value: Decimal
    total_potential_profit: Decimal
    total_sold: int


class PurchaseSaleReport(BaseModel):
    """Purchase and sale summary for a given period."""

    model_config = ConfigDict(from_attributes=True)

    total_purchase: (
        Decimal  # sum of purchase_orders.total_amount (is_purchase_order=False)
    )
    total_purchase_returns: Decimal  # sum of purchase_returns.total_amount
    total_sales: Decimal  # sum of sales.total_amount (status=COMPLETED)
    total_sales_returns: Decimal  # 0 placeholder
    net_position: Decimal  # total_sales - total_purchase


class ProductSalesRow(BaseModel):
    """One product row in the per-product sales report."""

    model_config = ConfigDict(from_attributes=True)

    product_id: uuid.UUID
    sku: str
    product_name: str
    category: str | None
    quantity_sold: int
    total_revenue: Decimal
    avg_unit_price: Decimal
    return_quantity: int
    net_quantity: int  # quantity_sold - return_quantity


class ProductSalesReport(BaseModel):
    """Paginated per-product sales report."""

    model_config = ConfigDict(from_attributes=True)

    rows: list[ProductSalesRow]
    total_revenue: Decimal
    period_start: date | None
    period_end: date | None
    total: int
    page: int
    page_size: int


class TrendingProductRow(BaseModel):
    """One product row in the trending products report."""

    model_config = ConfigDict(from_attributes=True)

    rank: int
    product_id: uuid.UUID
    product_name: str
    sku: str
    category: str | None
    quantity_sold: int
    total_revenue: Decimal


class TrendingProductsReport(BaseModel):
    """Top-N trending products for a period."""

    model_config = ConfigDict(from_attributes=True)

    rows: list[TrendingProductRow]
    period_start: date | None
    period_end: date | None
