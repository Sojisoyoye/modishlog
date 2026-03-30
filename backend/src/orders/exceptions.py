# TODO: Domain-specific exceptions for the Orders domain
#
# OrderNotFoundError(Exception)
#   - Raised when a purchase order lookup by ID yields no result.
#   - Attributes: order_id
#
# OrderNotEditableError(Exception)
#   - Raised when attempting to edit an order whose status does not allow modifications.
#   - Attributes: order_id, current_status
#
# InvalidStatusTransitionError(Exception)
#   - Raised when attempting a status transition that is not allowed by the workflow.
#   - Attributes: order_id, current_status, requested_status, allowed_transitions
#
# PaymentNotFoundError(Exception)
#   - Raised when a payment lookup by ID yields no result.
#   - Attributes: payment_id, order_id
#
# OverpaymentError(Exception)
#   - Raised when a payment would cause total payments to exceed the order total amount.
#   - Attributes: order_id, payment_amount, total_due, total_already_paid
#
# OrderLineItemError(Exception)
#   - Raised when an order has invalid line items (e.g. referencing non-existent products).
#   - Attributes: order_id, invalid_product_ids
