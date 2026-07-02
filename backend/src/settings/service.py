"""Settings service — encrypt/decrypt API keys and persist to DB."""

import asyncio
import base64
import hashlib
import time
import uuid
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.settings.models import AppSetting, BusinessProfile, UserApiKey, UserPreferences
from src.settings.schemas import BusinessProfileUpdate, FiscalYearRead

APP_SETTING_DEFAULTS: dict[str, str] = {
    "global_low_stock_threshold": "10",
    "default_currency_pair": "USDNGN",
    "invoice_footer_text": "",
    "invoice_default_notes": "",
    "default_payment_terms_days": "30",
}


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


async def get_business_profile(db: AsyncSession) -> BusinessProfile:
    result = await db.execute(select(BusinessProfile).limit(1))
    profile = result.scalar_one_or_none()
    if profile is None:
        # Use pg_insert with on_conflict_do_nothing to prevent duplicate rows
        # from concurrent first-time requests (SELECT-then-INSERT race).
        new_id = uuid.uuid4()
        stmt = pg_insert(BusinessProfile).values(id=new_id).on_conflict_do_nothing()
        await db.execute(stmt)
        await db.flush()
        result2 = await db.execute(select(BusinessProfile).limit(1))
        profile = result2.scalar_one()
    return profile


async def update_business_profile(
    db: AsyncSession,
    data: BusinessProfileUpdate,
    user_id: uuid.UUID,
) -> BusinessProfile:
    profile = await get_business_profile(db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    profile.updated_by = user_id
    await db.flush()
    return profile


async def get_app_settings(db: AsyncSession) -> dict[str, str | None]:
    result = await db.execute(select(AppSetting))
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
) -> None:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = value
        existing.updated_by = user_id
    else:
        db.add(AppSetting(key=key, value=value, updated_by=user_id))
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
