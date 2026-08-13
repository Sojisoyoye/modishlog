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


class PaymentAlreadyVoidedError(Exception):
    """Raised when attempting to edit a payment that's already VOIDED —
    void it, then record a fresh payment instead."""

    def __init__(self, payment_id: uuid.UUID, order_id: uuid.UUID) -> None:
        self.payment_id = payment_id
        self.order_id = order_id
        super().__init__(
            f"Payment {payment_id} on order {order_id} is voided and cannot "
            "be edited — record a new payment instead"
        )


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


class MissingFxRateError(Exception):
    """Raised when a payment's currency differs from the order's currency
    but no fx_rate was supplied to convert it."""

    def __init__(
        self, order_id: uuid.UUID, payment_currency: str, order_currency: str
    ) -> None:
        self.order_id = order_id
        self.payment_currency = payment_currency
        self.order_currency = order_currency
        super().__init__(
            f"fx_rate is required to record a {payment_currency} payment "
            f"against a {order_currency} order (order {order_id})"
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


class OrderNotDeliveredError(Exception):
    """Raised when a cost correction is attempted on an order that hasn't
    been delivered yet — use the normal order-edit flow for those instead,
    since no InventoryBatch/FIFO cost basis exists to cascade into."""

    def __init__(
        self, order_id: uuid.UUID, current_status: str, order_number: str | None = None
    ) -> None:
        self.order_id = order_id
        self.current_status = current_status
        label = order_number or order_id
        super().__init__(
            f"Order {label} is '{current_status}', not DELIVERED — cost "
            "corrections only apply to delivered orders (use the normal "
            "order edit for other statuses)"
        )


class LineItemNotFoundError(Exception):
    """Raised when a cost correction references a line item that doesn't
    belong to the given order."""

    def __init__(self, order_id: uuid.UUID, line_item_id: uuid.UUID) -> None:
        self.order_id = order_id
        self.line_item_id = line_item_id
        super().__init__(f"Line item {line_item_id} not found on order {order_id}")


class OrderAlreadyConsumedError(Exception):
    """Raised when attempting to revert a DELIVERED order's delivery after
    a sale has already drawn from the inventory batches it created —
    reverting would corrupt FIFO/COGS history, so it's blocked outright."""

    def __init__(self, order_id: uuid.UUID, order_number: str | None = None) -> None:
        self.order_id = order_id
        label = order_number or order_id
        super().__init__(
            f"Order {label} cannot be reverted from DELIVERED — one or "
            "more of its inventory batches has already been sold from"
        )


class PurchaseReturnNotFoundError(Exception):
    """Raised when a purchase return lookup by ID yields no result."""

    def __init__(self, return_id: uuid.UUID) -> None:
        self.return_id = return_id
        super().__init__(f"Purchase return {return_id} not found")
