# TODO: Pydantic schemas for the Orders domain
#
# --- Purchase Order Schemas ---
# OrderLineItemCreate
#   - product_id: UUID
#   - quantity: int (> 0)
#   - unit_cost: Decimal
#   - notes: str | None
#
# OrderCreate
#   - supplier_name: str
#   - supplier_contact: str | None
#   - currency: str = "USD"
#   - fx_rate_at_creation: Decimal | None
#   - expected_delivery_date: date | None
#   - notes: str | None
#   - line_items: list[OrderLineItemCreate] (at least one required)
#
# OrderUpdate
#   - supplier_name: str | None
#   - supplier_contact: str | None
#   - expected_delivery_date: date | None
#   - notes: str | None
#   - line_items: list[OrderLineItemCreate] | None (replaces all line items if provided)
#
# OrderLineItemRead
#   - id: UUID
#   - product_id: UUID
#   - product_name: str
#   - quantity: int
#   - unit_cost: Decimal
#   - line_total: Decimal
#
# OrderRead
#   - id: UUID
#   - order_number: str
#   - supplier_name, supplier_contact
#   - status: str
#   - total_amount: Decimal
#   - currency: str
#   - fx_rate_at_creation: Decimal | None
#   - expected_delivery_date: date | None
#   - actual_delivery_date: date | None
#   - notes: str | None
#   - line_items: list[OrderLineItemRead]
#   - payment_summary: PaymentSummary (nested)
#   - created_by: UUID
#   - created_at, updated_at: datetime
#
# OrderListResponse
#   - items: list[OrderRead]
#   - total: int
#   - page: int
#   - page_size: int
#
# --- Status Workflow Schemas ---
# StatusTransition
#   - new_status: str (validated against allowed transitions)
#   - notes: str | None
#
# StatusHistoryRead
#   - id: UUID
#   - from_status: str | None
#   - to_status: str
#   - transitioned_by: UUID
#   - notes: str | None
#   - created_at: datetime
#
# --- Payment Schemas ---
# PaymentCreate
#   - amount: Decimal (> 0)
#   - currency: str
#   - payment_date: date
#   - payment_method: str
#   - reference: str | None
#   - notes: str | None
#
# PaymentRead
#   - id: UUID
#   - order_id: UUID
#   - amount: Decimal
#   - currency: str
#   - payment_date: date
#   - payment_method: str
#   - reference: str | None
#   - status: str
#   - notes: str | None
#   - recorded_by: UUID
#   - created_at: datetime
#
# PaymentSummary
#   - total_due: Decimal
#   - total_paid: Decimal
#   - balance_remaining: Decimal
#   - payment_count: int
#   - is_fully_paid: bool
