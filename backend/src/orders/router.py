from fastapi import APIRouter

router = APIRouter()

# TODO: Planned endpoints for the Orders domain:
#
# --- Purchase Order CRUD ---
# POST   /orders/                           - Create a new purchase order (supplier, line items, expected delivery)
# GET    /orders/                           - List all orders with filters (status, supplier, date range)
# GET    /orders/{order_id}                 - Retrieve a single order with line items and payment info
# PUT    /orders/{order_id}                 - Update order details (line items, expected dates, notes)
# DELETE /orders/{order_id}                 - Cancel an order (only if status is "Pending")
#
# --- Order Status Workflow ---
# PUT    /orders/{order_id}/status           - Transition order to next status in workflow
#                                              Workflow: Pending -> In Production -> Shipping -> Cleared -> Delivered
# GET    /orders/{order_id}/status-history   - Get full status transition history for an order
# GET    /orders/by-status/{status}          - List all orders at a given status stage
#
# --- Payment Tracking ---
# POST   /orders/{order_id}/payments         - Record a payment against an order (amount, date, method, reference)
# GET    /orders/{order_id}/payments         - List all payments made for an order
# GET    /orders/{order_id}/payment-summary  - Payment summary (total due, total paid, balance remaining)
# PUT    /orders/{order_id}/payments/{payment_id} - Update a payment record
# DELETE /orders/{order_id}/payments/{payment_id} - Void a payment record
#
# --- Order Reporting ---
# GET    /orders/summary                     - Order summary dashboard (total orders, by status, total value)
# GET    /orders/overdue                     - List orders past their expected delivery date
