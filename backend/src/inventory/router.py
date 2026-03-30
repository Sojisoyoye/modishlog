from fastapi import APIRouter

router = APIRouter()

# TODO: Planned endpoints for the Inventory domain:
#
# --- Stock Levels ---
# GET    /inventory/                          - List current stock levels for all products (with filters)
# GET    /inventory/{product_id}              - Get current stock level for a specific product
# POST   /inventory/adjust                    - Manually adjust stock (add/remove with reason: received, damaged, correction)
# GET    /inventory/{product_id}/history       - Stock movement history for a product (all ins/outs)
#
# --- Low Stock Alerts ---
# GET    /inventory/alerts                     - List all active low-stock alerts
# PUT    /inventory/{product_id}/threshold     - Set or update the low-stock threshold for a product
# GET    /inventory/alerts/settings            - Get alert configuration (thresholds, notification preferences)
# PUT    /inventory/alerts/settings            - Update alert configuration
#
# --- Depletion Forecast ---
# GET    /inventory/{product_id}/forecast      - Forecast stock depletion for a product (days until stockout)
# GET    /inventory/forecast                   - Bulk depletion forecast for all products (sortable by urgency)
#
# --- Auto-Depletion from Sales ---
# POST   /inventory/deplete                    - Deplete stock based on a sale event (called internally by sales service)
# POST   /inventory/reverse                    - Reverse a depletion (called when a sale is voided)
# GET    /inventory/depletion-log              - View log of all automatic depletions (linked to sales)
