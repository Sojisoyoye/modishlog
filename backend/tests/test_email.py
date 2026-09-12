"""Tests for src/core/email.py -- transactional email sending.

TDD: written before the implementation.
"""

from unittest.mock import patch


class TestSendEmail:
    def test_noop_when_emails_disabled(self, monkeypatch):
        """When RESEND_API_KEY is unset, send_email must not call the Resend
        SDK at all -- keeps local dev/CI/pytest working with zero config."""
        from src.core import email as email_module
        from src.core.config import settings

        monkeypatch.setattr(settings, "RESEND_API_KEY", "")
        with patch("resend.Emails.send") as mock_send:
            email_module.send_email(
                email_to="user@example.com", subject="Hi", html_content="<p>hi</p>"
            )
        mock_send.assert_not_called()

    def test_calls_resend_when_enabled(self, monkeypatch):
        from src.core import email as email_module
        from src.core.config import settings

        monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_key")
        with patch("resend.Emails.send", return_value={"id": "abc123"}) as mock_send:
            email_module.send_email(
                email_to="user@example.com", subject="Hi", html_content="<p>hi</p>"
            )
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[0][0]
        assert call_kwargs["to"] == ["user@example.com"]
        assert call_kwargs["subject"] == "Hi"
        assert call_kwargs["html"] == "<p>hi</p>"


class TestEmailsEnabledSetting:
    def test_disabled_without_api_key(self, monkeypatch):
        from src.core.config import settings

        monkeypatch.setattr(settings, "RESEND_API_KEY", "")
        assert settings.emails_enabled is False

    def test_enabled_with_api_key(self, monkeypatch):
        from src.core.config import settings

        monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test_key")
        assert settings.emails_enabled is True


class TestRenderVerificationEmail:
    def test_includes_token_link(self, monkeypatch):
        from src.core import email as email_module
        from src.core.config import settings

        monkeypatch.setattr(settings, "FRONTEND_URL", "https://app.modishlog.com")
        subject, html = email_module.render_verification_email(
            "user@example.com", "abc123token"
        )
        assert "abc123token" in html
        assert "https://app.modishlog.com/verify-email?token=abc123token" in html
        assert subject

    def test_uses_brand_styling(self, monkeypatch):
        from src.core import email as email_module
        from src.core.config import settings

        monkeypatch.setattr(settings, "FRONTEND_URL", "https://app.modishlog.com")
        _, html = email_module.render_verification_email(
            "user@example.com", "abc123token"
        )
        assert "#059669" in html
        assert ">M<" in html


class TestRenderResetPasswordEmail:
    def test_includes_token_link(self, monkeypatch):
        from src.core import email as email_module
        from src.core.config import settings

        monkeypatch.setattr(settings, "FRONTEND_URL", "https://app.modishlog.com")
        subject, html = email_module.render_reset_password_email(
            "user@example.com", "resettoken456"
        )
        assert "resettoken456" in html
        assert "https://app.modishlog.com/reset-password?token=resettoken456" in html
        assert subject

    def test_uses_brand_styling(self, monkeypatch):
        from src.core import email as email_module
        from src.core.config import settings

        monkeypatch.setattr(settings, "FRONTEND_URL", "https://app.modishlog.com")
        _, html = email_module.render_reset_password_email(
            "user@example.com", "resettoken456"
        )
        assert "#059669" in html
        assert ">M<" in html
