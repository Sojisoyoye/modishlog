# TODO: SQLAlchemy models for the Sales domain
#
# Sale
#   - id: UUID primary key
#   - product_id: ForeignKey -> Product.id
#   - quantity: Integer, required, > 0
#   - unit_price: Numeric(12, 2) - price at the time of sale
#   - total_amount: Numeric(12, 2) - computed: quantity * unit_price
#   - currency: String(3), default "NGN"
#   - sale_date: Date, indexed
#   - channel: String (e.g. "online", "retail", "wholesale")
#   - status: String (e.g. "completed", "voided", "pending")
#   - notes: Text, optional
#   - recorded_by: ForeignKey -> User.id
#   - created_at: DateTime with timezone
#   - updated_at: DateTime with timezone
#
# SaleBulkUploadJob
#   - id: UUID primary key
#   - filename: String
#   - status: String ("pending", "processing", "completed", "failed", "partial")
#   - total_rows: Integer
#   - processed_rows: Integer, default 0
#   - successful_rows: Integer, default 0
#   - failed_rows: Integer, default 0
#   - error_details: JSON (list of {row, field, error} objects)
#   - uploaded_by: ForeignKey -> User.id
#   - created_at: DateTime with timezone
#   - completed_at: DateTime with timezone, nullable
#
# SaleAuditEntry
#   - id: UUID primary key
#   - sale_id: ForeignKey -> Sale.id
#   - action: String ("created", "updated", "voided")
#   - field_changes: JSON (dict of {field: {old, new}} pairs)
#   - performed_by: ForeignKey -> User.id
#   - reason: Text, optional
#   - created_at: DateTime with timezone
