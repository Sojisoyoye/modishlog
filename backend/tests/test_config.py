"""Tests for Settings validators in src/core/config.py."""

import pytest
from src.core.config import Settings


class TestEnsureAsyncpgDriver:
    def _make(self, url: str) -> str:
        s = Settings(DATABASE_URL=url)
        return s.DATABASE_URL

    def test_postgres_scheme_rewritten(self):
        assert self._make("postgres://user:pass@host/db").startswith(
            "postgresql+asyncpg://"
        )

    def test_postgresql_scheme_rewritten(self):
        assert self._make("postgresql://user:pass@host/db").startswith(
            "postgresql+asyncpg://"
        )

    def test_asyncpg_scheme_unchanged(self):
        url = "postgresql+asyncpg://user:pass@host/db"
        assert self._make(url) == url

    def test_query_params_preserved(self):
        result = self._make("postgresql://user:pass@host/db?sslmode=require")
        assert result == "postgresql+asyncpg://user:pass@host/db?sslmode=require"

    def test_postgres_scheme_only_replaces_prefix(self):
        # Ensure 'postgres://' inside the rest of the URL isn't touched
        result = self._make("postgresql://user:pass@host/postgres://db")
        assert result.startswith("postgresql+asyncpg://")
        assert result.count("postgresql+asyncpg://") == 1


class TestParseCorsOrigins:
    def test_comma_separated_string(self):
        s = Settings(CORS_ORIGINS="http://localhost:4200,https://example.com")
        assert s.CORS_ORIGINS == ["http://localhost:4200", "https://example.com"]

    def test_json_array_string(self):
        s = Settings(CORS_ORIGINS='["http://localhost:4200","https://example.com"]')
        assert s.CORS_ORIGINS == ["http://localhost:4200", "https://example.com"]

    def test_list_passthrough(self):
        origins = ["http://localhost:4200"]
        s = Settings(CORS_ORIGINS=origins)
        assert s.CORS_ORIGINS == origins

    def test_strips_whitespace(self):
        s = Settings(CORS_ORIGINS=" http://localhost:4200 , https://example.com ")
        assert s.CORS_ORIGINS == ["http://localhost:4200", "https://example.com"]
