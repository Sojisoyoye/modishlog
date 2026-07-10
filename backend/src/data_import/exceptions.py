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
