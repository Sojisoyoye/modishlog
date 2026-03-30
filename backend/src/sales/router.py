from fastapi import APIRouter

router = APIRouter()

# TODO: Planned endpoints for the Sales domain:
#
# --- Daily Sales Entry ---
# POST   /sales/                        - Record a single sale (product_id, quantity, unit_price, sale_date, channel)
# GET    /sales/                        - List sales with filters (date range, product, channel, status)
# GET    /sales/{sale_id}               - Retrieve a single sale record by ID
# PUT    /sales/{sale_id}               - Update a sale record (corrections, status changes)
# DELETE /sales/{sale_id}               - Void / cancel a sale (soft-delete with audit entry)
#
# --- Bulk CSV Upload ---
# POST   /sales/upload                  - Upload a CSV file of sales records for batch processing
# GET    /sales/upload/{job_id}/status   - Check the status of a bulk upload job (pending, processing, completed, failed)
# GET    /sales/upload/{job_id}/errors   - Retrieve row-level validation errors from a failed/partial upload
#
# --- Sales Audit Trail ---
# GET    /sales/{sale_id}/audit          - Retrieve the full audit trail for a specific sale
# GET    /sales/audit                    - List recent audit events across all sales (paginated)
#
# --- Sales History & Reporting ---
# GET    /sales/history                  - Aggregated sales history (daily, weekly, monthly roll-ups)
# GET    /sales/summary                  - Sales summary dashboard data (total revenue, units sold, top products)
# GET    /sales/by-product/{product_id}  - Sales history filtered by a specific product
# GET    /sales/by-channel               - Sales breakdown by channel (online, retail, wholesale)
