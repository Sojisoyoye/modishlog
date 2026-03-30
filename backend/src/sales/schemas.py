# TODO: Pydantic schemas for the Sales domain
#
# --- Sale Schemas ---
# SaleCreate
#   - product_id: UUID
#   - quantity: int (> 0)
#   - unit_price: Decimal
#   - sale_date: date
#   - channel: str (validated against allowed channels)
#   - notes: str | None
#
# SaleUpdate
#   - quantity: int | None
#   - unit_price: Decimal | None
#   - sale_date: date | None
#   - channel: str | None
#   - status: str | None
#   - notes: str | None
#
# SaleRead
#   - id: UUID
#   - product_id: UUID
#   - product_name: str (joined from Product)
#   - quantity, unit_price, total_amount, currency
#   - sale_date, channel, status, notes
#   - recorded_by: UUID
#   - created_at, updated_at: datetime
#
# SaleListResponse
#   - items: list[SaleRead]
#   - total: int
#   - page: int
#   - page_size: int
#
# --- Bulk Upload Schemas ---
# BulkUploadResponse
#   - job_id: UUID
#   - status: str
#   - message: str
#
# BulkUploadStatus
#   - job_id: UUID
#   - status: str
#   - total_rows, processed_rows, successful_rows, failed_rows: int
#   - completed_at: datetime | None
#
# BulkUploadError
#   - row: int
#   - field: str
#   - error: str
#
# --- Audit Schemas ---
# AuditEntryRead
#   - id: UUID
#   - sale_id: UUID
#   - action: str
#   - field_changes: dict
#   - performed_by: UUID
#   - reason: str | None
#   - created_at: datetime
#
# --- Reporting Schemas ---
# SalesSummary
#   - period: str (e.g. "2026-03")
#   - total_revenue: Decimal
#   - total_units_sold: int
#   - transaction_count: int
#   - top_products: list[dict] (product_id, name, revenue, units)
#
# SalesHistoryEntry
#   - date: date
#   - revenue: Decimal
#   - units_sold: int
#   - transaction_count: int
