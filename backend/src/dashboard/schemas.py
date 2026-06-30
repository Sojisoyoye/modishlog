"""Dashboard domain — Pydantic schemas."""

from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer


class RecentSaleItem(BaseModel):
    """A single recent sale entry for the hero section."""

    product_name: str
    quantity: int
    revenue: str
    margin_pct: str | None


class DashboardSummaryResponse(BaseModel):
    """KPI summary totals for the dashboard overview."""

    total_sales: Decimal
    net: Decimal
    invoice_due: Decimal
    total_sell_return: Decimal
    total_sell_return_paid: Decimal
    total_purchase: Decimal
    purchase_due: Decimal
    total_purchase_return: Decimal
    total_purchase_return_paid: Decimal
    expense: Decimal
    transaction_count: int = 0
    yesterday_sales: Decimal = Decimal("0")
    recent_sales: list[RecentSaleItem] = Field(default_factory=list)

    @field_serializer(
        "total_sales",
        "net",
        "invoice_due",
        "total_sell_return",
        "total_sell_return_paid",
        "total_purchase",
        "purchase_due",
        "total_purchase_return",
        "total_purchase_return_paid",
        "expense",
        "yesterday_sales",
    )
    def serialize_decimal(self, value: Decimal) -> str:
        return f"{value:.2f}"

    model_config = {"from_attributes": True}
