import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    actor_user_id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    details: dict | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    items: list[AuditLogRead]
    total: int
    page: int
    page_size: int
