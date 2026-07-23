import uuid


class MigrationJobNotFoundError(Exception):
    def __init__(self, job_id: uuid.UUID) -> None:
        self.job_id = job_id
        super().__init__(f"Migration job {job_id} not found")


class InvalidJobStateError(Exception):
    """Raised when an operation is attempted from a job status that doesn't allow it."""

    def __init__(self, job_id: uuid.UUID, expected: str, actual: str) -> None:
        self.job_id = job_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Migration job {job_id} must be '{expected}' for this operation, is '{actual}'"
        )


class TransformError(Exception):
    """Raised when a row references an ID that cannot be resolved and cannot be ghosted."""

    def __init__(self, entity: str, row: int, message: str) -> None:
        self.entity = entity
        self.row = row
        self.message = message
        super().__init__(f"{entity} row {row}: {message}")


class UnsupportedSourceSystemError(Exception):
    def __init__(self, source_system: str, extraction_mode: str) -> None:
        self.source_system = source_system
        self.extraction_mode = extraction_mode
        super().__init__(
            f"No {extraction_mode} adapter registered for source system '{source_system}'"
        )


class MissingExtractedDataError(Exception):
    """Raised when an API-mode job has no cached extraction to work from.

    Should never happen in the normal flow (create_job extracts eagerly and
    fails the job on error) — this is a safety net so a missing cache
    (deleted from disk, non-persistent filesystem, corrupted job state)
    surfaces as an explicit error instead of silently validating/confirming
    an empty, zero-row "successful" import.
    """

    def __init__(self, job_id: uuid.UUID) -> None:
        self.job_id = job_id
        super().__init__(
            f"Migration job {job_id} has no cached extraction data — cannot proceed"
        )


class PurchaseOrderImportError(Exception):
    """Raised when load_purchase_orders() (which reuses the orders/inventory
    services unmodified) hits a failure from one of those domains — a
    referenced product/order went stale between validation and confirm, a
    status transition or stock adjustment was rejected, or a line item
    failed schema validation. Wraps the underlying error so the router only
    needs to know about this one data_import-owned exception, not every
    exception type orders/inventory happen to raise today.

    The message is a safe, generic client-facing string — the raw `cause`
    (which for a pydantic ValidationError includes field paths, input
    values, and an errors.pydantic.dev URL) is kept on `.cause` for the
    caller to log server-side, not echoed to the client (see PR #222).
    """

    def __init__(self, cause: Exception) -> None:
        self.cause = cause
        super().__init__(
            "Could not import one or more purchase orders — a referenced "
            "product, variant, or order may have changed since this job "
            "was validated. Try re-validating the job."
        )


class StockAdjustmentImportError(Exception):
    """Raised when load_stock_adjustments() (which reuses inventory/service's
    adjust_stock() unmodified) hits a failure from that domain — a
    referenced product/variant went stale between validation and confirm,
    or an adjustment would take stock negative. Wraps the underlying error
    so the router only needs to know about this one data_import-owned
    exception, mirroring PurchaseOrderImportError's rationale.
    """

    def __init__(self, cause: Exception) -> None:
        self.cause = cause
        super().__init__(
            "Could not import one or more stock adjustments — a referenced "
            "product or variant may have changed since this job was "
            "validated, or an adjustment would take stock negative. Try "
            "re-validating the job."
        )


class PurchaseOrderRollbackBlockedError(Exception):
    """Raised when rollback() would need to delete an imported PurchaseOrder
    that already has a real OrderPayment recorded against it. That payment
    was made by the business after the import (it isn't tagged with this
    migration_id — the loader never creates payments), so it's real money
    data, not import data: deleting the order would either violate the
    order_payments FK (no ON DELETE CASCADE) or silently destroy that
    payment record. Rollback refuses outright instead of doing either.
    """

    def __init__(self, job_id: uuid.UUID, blocked_order_ids: list[uuid.UUID]) -> None:
        self.job_id = job_id
        self.blocked_order_ids = blocked_order_ids
        super().__init__(
            f"Cannot roll back migration job {job_id}: {len(blocked_order_ids)} "
            "imported purchase order(s) have payments recorded against them "
            "since the import. Remove those payments first, or leave this "
            "import in place."
        )
