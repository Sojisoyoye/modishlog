"""Structured logging configuration using structlog."""

import logging
import re

import structlog

from src.core.config import settings

# S7: Pattern to detect and redact passwords in database/service URLs.
# Matches postgresql://user:password@host/db and similar schemes.
_URL_PASSWORD_PATTERN = re.compile(
    r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+\-.]*://)"
    r"(?P<userinfo>[^:@/]+)"
    r":(?P<password>[^@/]+)"
    r"(?P<rest>@.*)"
)


def sanitize_url(url: str) -> str:
    """Mask the password portion of a database connection URL.

    S7: Prevents credentials from being written to log files when logging
    database connection strings (e.g., in Alembic env.py or startup logs).

    Examples:
        postgresql+asyncpg://user:SuperSecret@host:5432/db
        → postgresql+asyncpg://user:***@host:5432/db

        postgresql+asyncpg://localhost/modishlog  (no credentials in the URL)
        → postgresql+asyncpg://localhost/modishlog  (unchanged)
    """
    if not url:
        return url
    match = _URL_PASSWORD_PATTERN.search(url)
    if match:
        return (
            match.group("scheme")
            + match.group("userinfo")
            + ":***"
            + match.group("rest")
        )
    return url


def setup_logging() -> None:
    """Configure structlog for the application."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if settings.ENVIRONMENT == "development"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger() -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger()
