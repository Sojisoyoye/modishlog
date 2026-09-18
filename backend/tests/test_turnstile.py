"""Tests for Cloudflare Turnstile CAPTCHA verification (task #250).

TDD: written before the implementation, per project convention.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx as httpx_mod
import pytest


class TestVerifyTurnstileToken:
    @pytest.mark.asyncio
    async def test_returns_true_without_http_call_when_not_configured(self):
        from src.core import turnstile

        with patch.object(turnstile.settings, "TURNSTILE_SECRET_KEY", ""):
            with patch.object(turnstile.httpx, "AsyncClient") as mock_client_cls:
                result = await turnstile.verify_turnstile_token("some-token")
        assert result is True
        mock_client_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_true_when_cloudflare_reports_success(self):
        from src.core import turnstile

        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(turnstile.settings, "TURNSTILE_SECRET_KEY", "sk_test"):
            with patch.object(turnstile.httpx, "AsyncClient", return_value=mock_client):
                result = await turnstile.verify_turnstile_token("real-token", remote_ip="1.2.3.4")
        assert result is True
        mock_client.post.assert_called_once()
        _, kwargs = mock_client.post.call_args
        assert kwargs["data"]["secret"] == "sk_test"
        assert kwargs["data"]["response"] == "real-token"
        assert kwargs["data"]["remoteip"] == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_false_when_cloudflare_reports_failure(self):
        from src.core import turnstile

        mock_response = MagicMock()
        mock_response.json.return_value = {"success": False, "error-codes": ["invalid-input-response"]}
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(turnstile.settings, "TURNSTILE_SECRET_KEY", "sk_test"):
            with patch.object(turnstile.httpx, "AsyncClient", return_value=mock_client):
                with patch.object(turnstile.logger, "awarning", new=AsyncMock()) as mock_warn:
                    result = await turnstile.verify_turnstile_token("bad-token")
        assert result is False
        mock_warn.assert_called_once()
        assert mock_warn.call_args[0][0] == "turnstile_verify_rejected"

    @pytest.mark.asyncio
    async def test_fails_closed_and_logs_distinctly_on_network_error(self):
        """CAPTCHA is the primary defense here (the existing rate limit is
        already known-beatable), so a Cloudflare outage must reject the
        signup, not silently disable abuse protection -- the inverse of
        task #226's fail-open reasoning. Must log a distinct event from a
        rejected-token failure so an outage is diagnosable as such."""
        from src.core import turnstile

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx_mod.TimeoutException("timed out"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(turnstile.settings, "TURNSTILE_SECRET_KEY", "sk_test"):
            with patch.object(turnstile.httpx, "AsyncClient", return_value=mock_client):
                with patch.object(turnstile.logger, "aerror", new=AsyncMock()) as mock_err:
                    result = await turnstile.verify_turnstile_token("some-token")
        assert result is False
        mock_err.assert_called_once()
        assert mock_err.call_args[0][0] == "turnstile_verify_network_error"

    @pytest.mark.asyncio
    async def test_fails_closed_on_malformed_non_json_response(self):
        """response.json() raises a plain JSONDecodeError (not an httpx
        exception) on a non-JSON body -- a malformed-but-200-OK response
        (e.g. Cloudflare serving an HTML error page) must still fail
        closed, not crash with an uncaught exception."""
        from src.core import turnstile

        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("not valid JSON")
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(turnstile.settings, "TURNSTILE_SECRET_KEY", "sk_test"):
            with patch.object(turnstile.httpx, "AsyncClient", return_value=mock_client):
                with patch.object(turnstile.logger, "aerror", new=AsyncMock()) as mock_err:
                    result = await turnstile.verify_turnstile_token("some-token")
        assert result is False
        mock_err.assert_called_once()

    @pytest.mark.asyncio
    async def test_fails_closed_when_response_is_valid_json_but_not_a_dict(self):
        """A well-formed-JSON-but-wrong-shape response (e.g. a bare list)
        must not crash on .get('success') -- fail closed instead."""
        from src.core import turnstile

        mock_response = MagicMock()
        mock_response.json.return_value = ["unexpected", "shape"]
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(turnstile.settings, "TURNSTILE_SECRET_KEY", "sk_test"):
            with patch.object(turnstile.httpx, "AsyncClient", return_value=mock_client):
                with patch.object(turnstile.logger, "awarning", new=AsyncMock()):
                    result = await turnstile.verify_turnstile_token("some-token")
        assert result is False
