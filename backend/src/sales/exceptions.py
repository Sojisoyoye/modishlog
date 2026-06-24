"""Sales domain exceptions."""

import uuid


class SaleNotFoundError(Exception):
    """Raised when a sale lookup by ID yields no result."""

    def __init__(self, sale_id: uuid.UUID) -> None:
        self.sale_id = sale_id
        super().__init__(f"Sale {sale_id} not found")


class SaleAlreadyVoidedError(Exception):
    """Raised when attempting to update or void a sale that has already been voided."""

    def __init__(self, sale_id: uuid.UUID) -> None:
        self.sale_id = sale_id
        super().__init__(f"Sale {sale_id} has already been voided")


class BulkUploadJobNotFoundError(Exception):
    """Raised when referencing a bulk upload job that does not exist."""

    def __init__(self, job_id: uuid.UUID) -> None:
        self.job_id = job_id
        super().__init__(f"Bulk upload job {job_id} not found")


class InvalidCSVFormatError(Exception):
    """Raised when the uploaded CSV has missing/invalid headers or cannot be parsed."""

    def __init__(self, filename: str, details: str) -> None:
        self.filename = filename
        self.details = details
        super().__init__(f"Invalid CSV format in '{filename}': {details}")


class SalePermissionError(Exception):
    """Raised when a user attempts to access a sale they do not own."""

    def __init__(self, sale_id: uuid.UUID) -> None:
        self.sale_id = sale_id
        super().__init__(f"Access denied for sale {sale_id}")


class SaleValidationError(Exception):
    """Raised when sale data fails validation."""

    def __init__(self, field: str, value: object, reason: str) -> None:
        self.field = field
        self.value = value
        self.reason = reason
        super().__init__(f"Validation error on '{field}': {reason}")
