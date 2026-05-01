"""Application configuration using pydantic-settings."""

import json
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # Database — normalised to postgresql+asyncpg:// by validator below
    DATABASE_URL: str = "postgresql+asyncpg://modishlog:modishlog_dev@localhost:5433/modishlog"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def ensure_asyncpg_driver(cls, value: Any) -> str:
        """Normalise Neon/Heroku-style URLs for asyncpg.

        - Rewrites postgres:// and postgresql:// to postgresql+asyncpg://
        - Converts sslmode=require|verify-ca|verify-full to ssl=True (asyncpg
          does not accept the psycopg2-style sslmode parameter)
        """
        if not isinstance(value, str):
            return value
        for old in ("postgres://", "postgresql://"):
            if value.startswith(old):
                value = "postgresql+asyncpg://" + value[len(old):]
                break
        if "sslmode=" in value:
            parsed = urlparse(value)
            params = parse_qs(parsed.query, keep_blank_values=True)
            sslmode = params.pop("sslmode", [None])[0]
            if sslmode in ("require", "verify-ca", "verify-full"):
                params["ssl"] = ["True"]
            value = urlunparse(parsed._replace(query=urlencode({k: v[0] for k, v in params.items()})))
        return value

    # Security
    SECRET_KEY: str = "dev-secret-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

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


settings = Settings()
