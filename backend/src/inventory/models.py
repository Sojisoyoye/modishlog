# TODO: SQLAlchemy models for the Inventory domain
#
# StockLevel
#   - id: UUID primary key
#   - product_id: ForeignKey -> Product.id, unique (one row per product)
#   - quantity_on_hand: Integer, default 0
#   - quantity_reserved: Integer, default 0 (reserved for pending orders)
#   - quantity_available: Integer, computed (on_hand - reserved)
#   - low_stock_threshold: Integer, default 10
#   - last_replenished_at: DateTime, nullable
#   - updated_at: DateTime with timezone
#
# StockMovement
#   - id: UUID primary key
#   - product_id: ForeignKey -> Product.id
#   - movement_type: String ("sale_depletion", "sale_reversal", "manual_add", "manual_remove", "order_received", "damaged")
#   - quantity_change: Integer (positive for additions, negative for depletions)
#   - quantity_before: Integer
#   - quantity_after: Integer
#   - reference_id: UUID, nullable (sale_id, order_id, or adjustment_id)
#   - reference_type: String, nullable ("sale", "order", "adjustment")
#   - reason: Text, optional
#   - performed_by: ForeignKey -> User.id
#   - created_at: DateTime with timezone
#
# LowStockAlert
#   - id: UUID primary key
#   - product_id: ForeignKey -> Product.id
#   - threshold: Integer
#   - current_quantity: Integer
#   - status: String ("active", "acknowledged", "resolved")
#   - triggered_at: DateTime with timezone
#   - acknowledged_at: DateTime, nullable
#   - resolved_at: DateTime, nullable
