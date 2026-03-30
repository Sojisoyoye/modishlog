# TODO: SQLAlchemy models for the Orders domain
#
# PurchaseOrder
#   - id: UUID primary key
#   - order_number: String, unique, auto-generated (e.g. "PO-2026-00001")
#   - supplier_name: String, required
#   - supplier_contact: String, optional
#   - status: String, default "Pending"
#     Valid statuses: "Pending", "In Production", "Shipping", "Cleared", "Delivered", "Cancelled"
#   - total_amount: Numeric(14, 2) - sum of line items
#   - currency: String(3), default "USD" (purchase orders often in USD for imports)
#   - fx_rate_at_creation: Numeric(10, 4), nullable (NGN/USD rate when order was placed)
#   - expected_delivery_date: Date, nullable
#   - actual_delivery_date: Date, nullable
#   - notes: Text, optional
#   - created_by: ForeignKey -> User.id
#   - created_at: DateTime with timezone
#   - updated_at: DateTime with timezone
#
# OrderLineItem
#   - id: UUID primary key
#   - order_id: ForeignKey -> PurchaseOrder.id (cascade delete)
#   - product_id: ForeignKey -> Product.id
#   - quantity: Integer, required
#   - unit_cost: Numeric(12, 2)
#   - line_total: Numeric(12, 2) - computed: quantity * unit_cost
#   - notes: Text, optional
#
# OrderStatusHistory
#   - id: UUID primary key
#   - order_id: ForeignKey -> PurchaseOrder.id
#   - from_status: String, nullable (null for initial creation)
#   - to_status: String
#   - transitioned_by: ForeignKey -> User.id
#   - notes: Text, optional
#   - created_at: DateTime with timezone
#
# OrderPayment
#   - id: UUID primary key
#   - order_id: ForeignKey -> PurchaseOrder.id
#   - amount: Numeric(14, 2)
#   - currency: String(3)
#   - payment_date: Date
#   - payment_method: String (e.g. "bank_transfer", "lc", "cash")
#   - reference: String, optional (bank reference, LC number)
#   - status: String, default "completed" ("completed", "voided")
#   - notes: Text, optional
#   - recorded_by: ForeignKey -> User.id
#   - created_at: DateTime with timezone
