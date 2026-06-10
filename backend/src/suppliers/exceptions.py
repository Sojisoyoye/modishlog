"""Suppliers domain exceptions."""


class SupplierNotFoundError(Exception):
    """Raised when a supplier lookup yields no result."""

    def __init__(self, supplier_id=None):
        self.supplier_id = supplier_id
        super().__init__(f"Supplier not found: {supplier_id}")
