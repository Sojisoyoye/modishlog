# TODO: Pydantic schemas for the Products domain
#
# --- Product Schemas ---
# ProductCreate
#   - name: str (required)
#   - sku: str | None (optional; auto-generated if omitted)
#   - description: str | None
#   - category_id: UUID
#   - unit_cost: Decimal
#   - selling_price: Decimal
#   - currency: str = "NGN"
#
# ProductUpdate
#   - All fields optional (partial update support)
#   - name: str | None
#   - description: str | None
#   - category_id: UUID | None
#   - unit_cost: Decimal | None
#   - selling_price: Decimal | None
#   - is_active: bool | None
#
# ProductRead
#   - id: UUID
#   - name, sku, description, category_id, unit_cost, selling_price, currency, is_active
#   - created_at: datetime
#   - updated_at: datetime
#   - category: CategoryRead (nested)
#   - margin_pct: float (computed field: (selling_price - unit_cost) / selling_price)
#
# ProductListResponse
#   - items: list[ProductRead]
#   - total: int
#   - page: int
#   - page_size: int
#
# --- Category Schemas ---
# CategoryCreate
#   - name: str (required)
#   - description: str | None
#
# CategoryRead
#   - id: UUID
#   - name: str
#   - description: str | None
#   - product_count: int (computed)
#
# --- Price History Schemas ---
# PriceUpdateCreate
#   - new_unit_cost: Decimal | None
#   - new_selling_price: Decimal | None
#   - reason: str | None
#   - effective_date: date
#
# PriceHistoryRead
#   - id: UUID
#   - product_id: UUID
#   - old_unit_cost, new_unit_cost, old_selling_price, new_selling_price
#   - reason: str | None
#   - effective_date: date
#   - changed_by: UUID
#   - created_at: datetime
#
# MarginReport
#   - product_id: UUID
#   - product_name: str
#   - unit_cost: Decimal
#   - selling_price: Decimal
#   - margin_pct: float
#   - margin_amount: Decimal
