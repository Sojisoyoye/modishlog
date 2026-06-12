"""Settings service — encrypt/decrypt API keys and persist to DB."""

import base64
import hashlib
import uuid

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.settings.models import UserApiKey


def _fernet() -> Fernet:
    """Derive a Fernet key from the application SECRET_KEY via SHA-256."""
    raw = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    key = base64.urlsafe_b64encode(raw)
    return Fernet(key)


def encrypt_api_key(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()


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
