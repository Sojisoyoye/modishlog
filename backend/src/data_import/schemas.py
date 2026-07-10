import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from src.data_import.models import ExtractionMode, MigrationJobStatus, SourceSystem


class ValidationIssue(BaseModel):
    entity: str
    row: int
    field: str | None = None
    severity: str  # "error" | "warning"
    message: str


class MigrationJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    status: MigrationJobStatus
    source_system: SourceSystem
    extraction_mode: ExtractionMode
    row_counts: dict
    validation_errors: list
    validation_warnings: list
    created_at: datetime
    completed_at: datetime | None


class MigrationJobListResponse(BaseModel):
    items: list[MigrationJobRead]


class TestConnectionRequest(BaseModel):
    source_system: SourceSystem
    api_base_url: str
    username: str | None = None
    password: str | None = None
    access_token: str | None = None


class TestConnectionDateRange(BaseModel):
    earliest: str | None = None
    latest: str | None = None


class TestConnectionResponse(BaseModel):
    connected: bool
    source_system: SourceSystem
    counts: dict[str, int]
    date_range: TestConnectionDateRange | None = None


class SnapshotEntity(BaseModel):
    name: str
    count: int
    sample_rows: list[dict] = []
    date_range: TestConnectionDateRange | None = None


class ConfirmationSnapshot(BaseModel):
    job_id: uuid.UUID
    extraction_mode: ExtractionMode
    source_system: SourceSystem
    status: MigrationJobStatus
    entities: list[SnapshotEntity]
    warnings: list[ValidationIssue]
    ghost_records: dict[str, int]
    total_rows: int


class ConfirmRequest(BaseModel):
    approved: bool
