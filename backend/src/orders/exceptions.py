"""Orders domain exceptions."""

import uuid
from decimal import Decimal


class OrderNotFoundError(Exception):
    """Raised when a purchase order lookup by ID yields no result."""

    def __init__(self, order_id: uuid.UUID) -> None:
        self.order_id = order_id
        super().__init__(f"Order {order_id} not found")


class OrderNotEditableError(Exception):
    """Raised when attempting to edit an order whose status does not allow modifications."""

    def __init__(self, order_id: uuid.UUID, current_status: str) -> None:
        self.order_id = order_id
        self.current_status = current_status
        super().__init__(
            f"Order {order_id} cannot be edited in status '{current_status}'"
        )


class InvalidStatusTransitionError(Exception):
    """Raised when attempting a status transition not allowed by the workflow."""

    def __init__(
        self,
        order_id: uuid.UUID,
        current_status: str,
        requested_status: str,
        allowed: list[str],
    ) -> None:
        self.order_id = order_id
        self.current_status = current_status
        self.requested_status = requested_status
        self.allowed_transitions = allowed
        super().__init__(
            f"Cannot transition order {order_id} from '{current_status}' to "
            f"'{requested_status}'. Allowed: {allowed}"
        )


class PaymentNotFoundError(Exception):
    """Raised when a payment lookup by ID yields no result."""

    def __init__(self, payment_id: uuid.UUID, order_id: uuid.UUID) -> None:
        self.payment_id = payment_id
        self.order_id = order_id
        super().__init__(f"Payment {payment_id} not found for order {order_id}")


class OverpaymentError(Exception):
    """Raised when a payment would exceed the order total amount."""

    def __init__(
        self,
        order_id: uuid.UUID,
        payment_amount: Decimal,
        total_due: Decimal,
        total_already_paid: Decimal,
    ) -> None:
        self.order_id = order_id
        self.payment_amount = payment_amount
        self.total_due = total_due
        self.total_already_paid = total_already_paid
        balance = total_due - total_already_paid
        super().__init__(
            f"Payment of {payment_amount} exceeds remaining balance of {balance} "
            f"for order {order_id}"
        )


class OrderLineItemError(Exception):
    """Raised when an order has invalid line items."""

    def __init__(
        self, order_id: uuid.UUID | None, invalid_product_ids: list[uuid.UUID]
    ) -> None:
        self.order_id = order_id
        self.invalid_product_ids = invalid_product_ids
        super().__init__(
            f"Invalid product IDs in order: {[str(pid) for pid in invalid_product_ids]}"
        )


class PurchaseReturnNotFoundError(Exception):
    """Raised when a purchase return lookup by ID yields no result."""

    def __init__(self, return_id: uuid.UUID) -> None:
        self.return_id = return_id
        super().__init__(f"Purchase return {return_id} not found")
