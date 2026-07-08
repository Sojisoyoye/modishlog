"""Settings service — encrypt/decrypt API keys and persist to DB."""

import asyncio
import base64
import hashlib
import time
import uuid

import structlog
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.settings.models import AppSetting, BusinessProfile, UserApiKey, UserPreferences
from src.settings.schemas import BusinessProfileUpdate, FiscalYearRead

logger = structlog.get_logger()

APP_SETTING_DEFAULTS: dict[str, str] = {
    "global_low_stock_threshold": "10",
    "default_currency_pair": "USDNGN",
    "invoice_footer_text": "",
    "invoice_default_notes": "",
    "default_payment_terms_days": "30",
}


def _get_fernet_keys() -> list[Fernet]:
    """Return an ordered list of Fernet instances for key rotation.

    S5: Supports FERNET_KEYS as a comma-separated list of raw key material.
    The first entry is used for encryption (newest key); all entries are tried
    for decryption to support seamless key rotation.

    If FERNET_KEYS is empty, falls back to deriving a key from SECRET_KEY
    (legacy behaviour, maintains backward compatibility).
    """
    fernet_instances: list[Fernet] = []

    if settings.FERNET_KEYS:
        raw_keys = [k.strip() for k in settings.FERNET_KEYS.split(",") if k.strip()]
        if not raw_keys:
            raise ValueError(
                "FERNET_KEYS is set but contains no valid keys — "
                "check for empty strings or whitespace-only values."
            )
        for raw in raw_keys:
            derived = hashlib.sha256(raw.encode()).digest()
            key = base64.urlsafe_b64encode(derived)
            fernet_instances.append(Fernet(key))
        return fernet_instances

    # Legacy: derive from SECRET_KEY
    raw = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    key = base64.urlsafe_b64encode(raw)
    return [Fernet(key)]


def encrypt_api_key(plaintext: str) -> str:
    """Encrypt using the primary (newest) key."""
    return _get_fernet_keys()[0].encrypt(plaintext.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    """Decrypt by trying each key in rotation order.

    S5: Tries the newest key first; if decryption fails, tries each subsequent
    key in the rotation list. This allows old ciphertext to be read after
    key rotation without requiring re-encryption of all existing records.
    """
    keys = _get_fernet_keys()
    last_exc: Exception | None = None
    for fernet_instance in keys:
        try:
            return fernet_instance.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            last_exc = exc
    raise ValueError(
        "API key could not be decrypted — no matching Fernet key found in rotation list. "
        "Check FERNET_KEYS configuration."
    ) from last_exc


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
    month: int | None,
    day: int | None,
) -> FiscalYearRead:
    # Use INSERT … ON CONFLICT DO UPDATE to avoid a SELECT-then-INSERT race when
    # two concurrent requests arrive for a user with no existing preferences row.
    stmt = (
        pg_insert(UserPreferences)
        .values(
            id=uuid.uuid4(),
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


async def get_business_profile(
    db: AsyncSession, business_id: uuid.UUID
) -> BusinessProfile | None:
    """Return the BusinessProfile for the given business_id, or None if not found."""
    result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.business_id == business_id)
    )
    return result.scalar_one_or_none()


async def update_business_profile(
    db: AsyncSession,
    data: BusinessProfileUpdate,
    user_id: uuid.UUID,
    business_id: uuid.UUID,
) -> BusinessProfile:
    """Upsert a BusinessProfile for the given business_id.

    Uses INSERT … ON CONFLICT DO UPDATE to prevent duplicate-row races when two
    concurrent requests both find no existing profile for this business.
    """
    fields = data.model_dump(exclude_unset=True)
    fields["updated_by"] = user_id
    fields["business_id"] = business_id

    stmt = (
        pg_insert(BusinessProfile)
        .values(id=uuid.uuid4(), **fields)
        .on_conflict_do_update(
            index_elements=["business_id"],
            set_={**fields, "updated_at": func.now()},
        )
    )
    await db.execute(stmt)
    await db.flush()
    # Re-fetch so the caller always receives a fully-populated ORM object.
    profile = await get_business_profile(db, business_id)
    assert profile is not None  # guaranteed by the upsert above
    return profile


async def get_app_setting(
    db: AsyncSession, key: str, business_id: uuid.UUID
) -> AppSetting | None:
    """Return a single AppSetting row for the given key and business_id."""
    result = await db.execute(
        select(AppSetting).where(
            AppSetting.key == key,
            AppSetting.business_id == business_id,
        )
    )
    return result.scalar_one_or_none()


async def get_app_settings(
    db: AsyncSession, business_id: uuid.UUID
) -> dict[str, str | None]:
    """Return all app settings for the given business, merged with defaults."""
    result = await db.execute(
        select(AppSetting).where(AppSetting.business_id == business_id)
    )
    rows = result.scalars().all()
    merged = dict(APP_SETTING_DEFAULTS)
    for row in rows:
        merged[row.key] = row.value
    return merged


async def update_app_setting(
    db: AsyncSession,
    key: str,
    value: str,
    user_id: uuid.UUID,
    business_id: uuid.UUID,
) -> None:
    """Upsert an app setting for the given business_id.

    Uses INSERT … ON CONFLICT DO UPDATE to prevent duplicate-row races when two
    concurrent requests both find no existing row for this (key, business_id) pair.
    """
    stmt = (
        pg_insert(AppSetting)
        .values(key=key, business_id=business_id, value=value, updated_by=user_id)
        .on_conflict_do_update(
            index_elements=["key", "business_id"],
            set_={"value": value, "updated_by": user_id, "updated_at": func.now()},
        )
    )
    await db.execute(stmt)
    await db.flush()


def _call_anthropic_api(key: str) -> bool:
    try:
        import anthropic  # type: ignore[import]

        anthropic.Anthropic(api_key=key).models.list()
        return True
    except Exception:
        return False


async def test_anthropic_api_key(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    result = await db.execute(
        select(UserApiKey).where(
            UserApiKey.user_id == user_id,
            UserApiKey.key_name == "anthropic",
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return {"success": False, "message": "Anthropic API key not configured", "latency_ms": None}
    plaintext = decrypt_api_key(row.encrypted_value)
    start = time.monotonic()
    # Run the synchronous HTTP call in a thread to avoid blocking the event loop.
    ok = await asyncio.to_thread(_call_anthropic_api, plaintext)
    latency_ms = int((time.monotonic() - start) * 1000)
    if ok:
        return {"success": True, "message": "Connection successful", "latency_ms": latency_ms}
    return {"success": False, "message": "API key test failed — check key and permissions", "latency_ms": latency_ms}
