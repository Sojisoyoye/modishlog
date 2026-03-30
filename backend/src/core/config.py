"""Application configuration using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://modishlog:modishlog_dev@localhost/modishlog"

    # Security
    SECRET_KEY: str = "dev-secret-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:4200"]

    # Environment
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "info"

    # External APIs
    FX_API_KEY: str = ""
    FX_API_URL: str = "https://api.example.com/fx"


settings = Settings()
