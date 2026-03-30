# TODO: Async service functions for the Sales domain
#
# --- Daily Sales Entry ---
# async def create_sale(db, sale_in: SaleCreate, user_id: UUID) -> Sale
#   - Validate product exists and is active
#   - Compute total_amount = quantity * unit_price
#   - Create Sale record with status "completed"
#   - Create initial SaleAuditEntry (action="created")
#   - Trigger inventory depletion event (publish to inventory service)
#
# async def get_sale(db, sale_id: UUID) -> Sale
#   - Fetch sale with product relationship loaded
#   - Raise SaleNotFoundError if missing
#
# async def list_sales(db, filters: dict, page: int, page_size: int) -> tuple[list[Sale], int]
#   - Support filtering by: date range, product_id, channel, status
#   - Paginate and return (items, total_count)
#
# async def update_sale(db, sale_id: UUID, sale_in: SaleUpdate, user_id: UUID) -> Sale
#   - Fetch existing, raise SaleNotFoundError if missing
#   - Raise SaleAlreadyVoidedError if status is "voided"
#   - Log field changes to SaleAuditEntry
#   - If quantity changed, trigger inventory adjustment event
#
# async def void_sale(db, sale_id: UUID, reason: str, user_id: UUID) -> Sale
#   - Soft-delete: set status = "voided"
#   - Create audit entry with reason
#   - Trigger inventory reversal event (restore stock)
#
# --- Bulk CSV Upload ---
# async def process_bulk_upload(db, file: UploadFile, user_id: UUID) -> SaleBulkUploadJob
#   - Create SaleBulkUploadJob with status "pending"
#   - Parse CSV, validate headers
#   - Kick off background task for row-by-row processing
#
# async def process_upload_rows(db, job_id: UUID) -> None
#   - Background task: iterate rows, validate each, create Sale records
#   - Track successful/failed rows, store error_details JSON
#   - Update job status on completion
#
# async def get_upload_status(db, job_id: UUID) -> SaleBulkUploadJob
# async def get_upload_errors(db, job_id: UUID) -> list[dict]
#
# --- Sales Audit Trail ---
# async def get_sale_audit_trail(db, sale_id: UUID) -> list[SaleAuditEntry]
# async def list_recent_audit_events(db, page: int, page_size: int) -> tuple[list[SaleAuditEntry], int]
#
# --- Sales History & Reporting ---
# async def get_sales_history(db, granularity: str, date_from: date, date_to: date) -> list[SalesHistoryEntry]
#   - Aggregate by day, week, or month
#
# async def get_sales_summary(db, date_from: date, date_to: date) -> SalesSummary
#   - Total revenue, units, transaction count, top products
#
# async def get_sales_by_product(db, product_id: UUID, date_from: date, date_to: date) -> list[SalesHistoryEntry]
# async def get_sales_by_channel(db, date_from: date, date_to: date) -> dict[str, SalesSummary]
