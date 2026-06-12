"""Settings domain — user-scoped API keys stored encrypted at rest."""

import uuid as _uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin


class UserApiKey(UUIDMixin, TimestampMixin, Base):
    """Per-user API key stored encrypted with Fernet."""

    __tablename__ = "user_api_keys"

    user_id: Mapped[_uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    key_name: Mapped[str] = mapped_column(String(100))
    encrypted_value: Mapped[str] = mapped_column(Text)
