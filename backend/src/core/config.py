"""Application configuration using pydantic-settings."""

import json
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# libpq-style query params that asyncpg does not accept as URL query params.
# SSL is handled via connect_args={"ssl": True} on the engine instead.
_LIBPQ_DROP = frozenset(
    {
        "sslmode", "sslrootcert", "sslcert", "sslkey", "sslpassword",
        "channel_binding", "gssencmode", "krbsrvname", "gsslib",
        "target_session_attrs", "connect_timeout", "keepalives",
        "keepalives_idle", "keepalives_interval", "keepalives_count",
        "application_name", "fallback_application_name",
        "load_balance_hosts", "options",
    }
)

_SSL_REQUIRED_MODES = frozenset({"require", "verify-ca", "verify-full"})


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Database — normalised to postgresql+asyncpg:// with libpq params stripped
    DATABASE_URL: str = "postgresql+asyncpg://modishlog:modishlog_dev@localhost:5433/modishlog"
    # True when the original DATABASE_URL contained sslmode=require|verify-*
    DATABASE_SSL: bool = False

    @model_validator(mode="before")
    @classmethod
    def detect_ssl(cls, data: Any) -> Any:
        """Detect SSL requirement from the raw DATABASE_URL before field validation."""
        if isinstance(data, dict):
            url = data.get("DATABASE_URL", "")
            if isinstance(url, str) and "sslmode=" in url:
                parsed = urlparse(url)
                params = parse_qs(parsed.query, keep_blank_values=True)
                sslmode = (params.get("sslmode") or [None])[0]
                if sslmode in _SSL_REQUIRED_MODES:
                    data["DATABASE_SSL"] = True
        return data

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def ensure_asyncpg_driver(cls, value: Any) -> str:
        """Normalise Neon/Heroku-style URLs for asyncpg.

        - Rewrites postgres:// and postgresql:// to postgresql+asyncpg://
        - Strips all libpq query params (sslmode, channel_binding, etc.)
          SSL is configured via DATABASE_SSL + connect_args on the engine.
        """
        if not isinstance(value, str):
            return value
        for old in ("postgres://", "postgresql://"):
            if value.startswith(old):
                value = "postgresql+asyncpg://" + value[len(old):]
                break
        parsed = urlparse(value)
        if parsed.query:
            params = parse_qs(parsed.query, keep_blank_values=True)
            for key in _LIBPQ_DROP:
                params.pop(key, None)
            value = urlunparse(
                parsed._replace(query=urlencode({k: v[0] for k, v in params.items()}))
            )
        return value

    # Security
    SECRET_KEY: str = "dev-secret-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS — accepts a JSON array string or comma-separated string from env vars
    CORS_ORIGINS: list[str] = ["http://localhost:4200"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                return json.loads(value)
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    # File uploads — /app/uploads is writable by appuser in Docker
    UPLOAD_DIR: str = "/app/uploads"

    # Environment
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "info"

    # External APIs
    FX_API_KEY: str = ""
    FX_API_URL: str = "https://api.example.com/fx"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com"


settings = Settings()
