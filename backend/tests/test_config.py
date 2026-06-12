"""Tests for Settings validators in src/core/config.py."""

from src.core.config import Settings


class TestEnsureAsyncpgDriver:
    def _make(self, url: str) -> Settings:
        return Settings(DATABASE_URL=url)

    def test_postgres_scheme_rewritten(self):
        s = self._make("postgres://user:pass@host/db")
        assert s.DATABASE_URL.startswith("postgresql+asyncpg://")

    def test_postgresql_scheme_rewritten(self):
        s = self._make("postgresql://user:pass@host/db")
        assert s.DATABASE_URL.startswith("postgresql+asyncpg://")

    def test_asyncpg_scheme_unchanged(self):
        url = "postgresql+asyncpg://user:pass@host/db"
        assert self._make(url).DATABASE_URL == url

    def test_postgres_scheme_only_replaces_prefix(self):
        s = self._make("postgresql://user:pass@host/postgres://db")
        assert s.DATABASE_URL.startswith("postgresql+asyncpg://")
        assert s.DATABASE_URL.count("postgresql+asyncpg://") == 1

    def test_sslmode_require_stripped_ssl_flag_set(self):
        s = self._make("postgresql://user:pass@host/db?sslmode=require")
        assert "sslmode" not in s.DATABASE_URL
        assert s.DATABASE_SSL is True

    def test_sslmode_verify_ca_stripped_ssl_flag_set(self):
        s = self._make("postgresql://user:pass@host/db?sslmode=verify-ca")
        assert "sslmode" not in s.DATABASE_URL
        assert s.DATABASE_SSL is True

    def test_sslmode_disable_stripped_no_ssl_flag(self):
        s = self._make("postgresql://user:pass@host/db?sslmode=disable")
        assert "sslmode" not in s.DATABASE_URL
        assert s.DATABASE_SSL is False

    def test_channel_binding_stripped(self):
        s = self._make(
            "postgresql://user:pass@host/db?sslmode=require&channel_binding=require"
        )
        assert "channel_binding" not in s.DATABASE_URL
        assert s.DATABASE_SSL is True

    def test_all_libpq_params_stripped(self):
        s = self._make(
            "postgresql://user:pass@host/db"
            "?sslmode=require&channel_binding=require&connect_timeout=10"
            "&application_name=myapp&sslrootcert=/path/to/cert"
        )
        assert "sslmode" not in s.DATABASE_URL
        assert "channel_binding" not in s.DATABASE_URL
        assert "connect_timeout" not in s.DATABASE_URL
        assert "application_name" not in s.DATABASE_URL
        assert "sslrootcert" not in s.DATABASE_URL
        assert s.DATABASE_SSL is True

    def test_no_ssl_by_default(self):
        s = self._make("postgresql+asyncpg://user:pass@host/db")
        assert s.DATABASE_SSL is False


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


class TestSecretKeyValidation:
    def _make(self, secret: str) -> Settings:
        return Settings(SECRET_KEY=secret)

    def test_strong_secret_key_accepted(self):
        s = self._make("a" * 32)
        assert s.SECRET_KEY == "a" * 32

    def test_dev_default_secret_key_rejected(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            self._make("dev-secret-change-in-production")

    def test_short_secret_key_rejected(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            self._make("tooshort")

    def test_exactly_32_chars_accepted(self):
        s = self._make("x" * 32)
        assert len(s.SECRET_KEY) == 32
