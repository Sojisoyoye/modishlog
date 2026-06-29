"""Settings service — encrypt/decrypt API keys and persist to DB."""

import base64
import hashlib
import uuid
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.settings.models import UserApiKey, UserPreferences
from src.settings.schemas import FiscalYearRead


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """Derive a Fernet key from the application SECRET_KEY via SHA-256.

    Result is cached for the process lifetime — SECRET_KEY must not change
    after startup (rotation requires a restart).
    If a test patches settings.SECRET_KEY it must call _fernet.cache_clear()
    before and after the patch to avoid stale key cross-contamination.
    """
    raw = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    key = base64.urlsafe_b64encode(raw)
    return Fernet(key)


def encrypt_api_key(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError(
            "API key could not be decrypted — SECRET_KEY may have been rotated"
        ) from exc


async def upsert_api_key(
    db: AsyncSession,
    user_id: uuid.UUID,
    key_name: str,
    key_value: str,
) -> None:
    encrypted = encrypt_api_key(key_value)
    result = await db.execute(
        select(UserApiKey).where(
            UserApiKey.user_id == user_id,
            UserApiKey.key_name == key_name,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.encrypted_value = encrypted
    else:
        db.add(
            UserApiKey(user_id=user_id, key_name=key_name, encrypted_value=encrypted)
        )
    await db.flush()


async def get_api_key_status(
    db: AsyncSession,
    user_id: uuid.UUID,
    key_name: str,
) -> bool:
    result = await db.execute(
        select(UserApiKey).where(
            UserApiKey.user_id == user_id,
            UserApiKey.key_name == key_name,
        )
    )
    return result.scalar_one_or_none() is not None


async def get_fiscal_year_start(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> FiscalYearRead:
    result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == user_id)
    )
    prefs = result.scalar_one_or_none()
    if prefs is None:
        return FiscalYearRead(fiscal_year_start_month=None, fiscal_year_start_day=None)
    return FiscalYearRead(
        fiscal_year_start_month=prefs.fiscal_year_start_month,
        fiscal_year_start_day=prefs.fiscal_year_start_day,
    )


async def update_fiscal_year_start(
    db: AsyncSession,
    user_id: uuid.UUID,
    month: Optional[int],
    day: Optional[int],
) -> FiscalYearRead:
    # Use INSERT … ON CONFLICT DO UPDATE to avoid a SELECT-then-INSERT race when
    # two concurrent requests arrive for a user with no existing preferences row.
    stmt = (
        pg_insert(UserPreferences)
        .values(
            user_id=user_id,
            fiscal_year_start_month=month,
            fiscal_year_start_day=day,
        )
        .on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "fiscal_year_start_month": month,
                "fiscal_year_start_day": day,
                # ORM onupdate hooks are bypassed by Core statements — bump explicitly.
                "updated_at": func.now(),
            },
        )
    )
    await db.execute(stmt)
    await db.flush()
    return FiscalYearRead(
        fiscal_year_start_month=month,
        fiscal_year_start_day=day,
    )
