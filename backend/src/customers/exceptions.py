"""Customers domain exceptions."""


class CustomerNotFoundError(Exception):
    """Raised when a customer lookup yields no result."""

    def __init__(self, customer_id=None):
        self.customer_id = customer_id
        super().__init__(f"Customer not found: {customer_id}")
