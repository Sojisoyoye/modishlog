"""Settings service — encrypt/decrypt API keys and persist to DB."""

import base64
import hashlib
import uuid
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.settings.models import UserApiKey


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
