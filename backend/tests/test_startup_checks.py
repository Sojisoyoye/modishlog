"""Tests for startup-time required-production-settings validation (task #230).

TDD: written before the implementation, per project convention.
"""

from unittest.mock import MagicMock, patch


class TestCheckRequiredProductionSettings:
    def test_no_warning_in_development_even_when_everything_missing(self):
        from src.main import check_required_production_settings

        mock_settings = MagicMock(
            ENVIRONMENT="development",
            REDIS_URL="",
            RESEND_API_KEY="",
            SENTRY_DSN="",
            FERNET_KEYS="",
        )
        with patch("src.main.settings", mock_settings):
            with patch("src.main.logger") as mock_logger:
                check_required_production_settings()
        mock_logger.warning.assert_not_called()

    def test_warns_with_all_missing_names_in_production(self):
        from src.main import check_required_production_settings

        mock_settings = MagicMock(
            ENVIRONMENT="production",
            REDIS_URL="",
            RESEND_API_KEY="",
            SENTRY_DSN="",
            FERNET_KEYS="",
        )
        with patch("src.main.settings", mock_settings):
            with patch("src.main.logger") as mock_logger:
                check_required_production_settings()
        mock_logger.warning.assert_called_once()
        _, kwargs = mock_logger.warning.call_args
        assert set(kwargs["missing"]) == {
            "REDIS_URL",
            "RESEND_API_KEY",
            "SENTRY_DSN",
            "FERNET_KEYS",
        }

    def test_warns_in_staging_too(self):
        from src.main import check_required_production_settings

        mock_settings = MagicMock(
            ENVIRONMENT="staging",
            REDIS_URL="",
            RESEND_API_KEY="re_123",
            SENTRY_DSN="",
            FERNET_KEYS="key1",
        )
        with patch("src.main.settings", mock_settings):
            with patch("src.main.logger") as mock_logger:
                check_required_production_settings()
        mock_logger.warning.assert_called_once()
        _, kwargs = mock_logger.warning.call_args
        assert set(kwargs["missing"]) == {"REDIS_URL", "SENTRY_DSN"}

    def test_no_warning_in_production_when_everything_set(self):
        from src.main import check_required_production_settings

        mock_settings = MagicMock(
            ENVIRONMENT="production",
            REDIS_URL="redis://redis:6379",
            RESEND_API_KEY="re_123",
            SENTRY_DSN="https://sentry.example/1",
            FERNET_KEYS="key1,key0",
        )
        with patch("src.main.settings", mock_settings):
            with patch("src.main.logger") as mock_logger:
                check_required_production_settings()
        mock_logger.warning.assert_not_called()

    def test_never_raises_regardless_of_what_is_missing(self):
        """A misconfigured deploy must still come up -- this only ever
        warns loudly, never hard-fails startup."""
        from src.main import check_required_production_settings

        mock_settings = MagicMock(
            ENVIRONMENT="production",
            REDIS_URL="",
            RESEND_API_KEY="",
            SENTRY_DSN="",
            FERNET_KEYS="",
        )
        with patch("src.main.settings", mock_settings):
            check_required_production_settings()  # must not raise
