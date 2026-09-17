"""Tests for the access-token revocation denylist (task #226).

TDD: written before the implementation, per project convention.
"""

from unittest.mock import AsyncMock, patch

import pytest


class TestRevokeJti:
    @pytest.mark.asyncio
    async def test_noop_when_redis_url_empty(self):
        from src.core import token_revocation

        with patch.object(token_revocation.settings, "REDIS_URL", ""):
            with patch.object(token_revocation, "_get_redis_client") as mock_get_client:
                await token_revocation.revoke_jti("some-jti", ttl_seconds=3600)
        mock_get_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_setex_with_jti_and_ttl(self):
        from src.core import token_revocation

        mock_client = AsyncMock()
        with patch.object(token_revocation.settings, "REDIS_URL", "redis://redis:6379"):
            with patch.object(token_revocation, "_get_redis_client", return_value=mock_client):
                await token_revocation.revoke_jti("some-jti", ttl_seconds=3600)
        mock_client.setex.assert_called_once()
        args, _ = mock_client.setex.call_args
        assert args[0] == "revoked_jti:some-jti"
        assert args[1] == 3600

    @pytest.mark.asyncio
    async def test_clamps_non_positive_ttl_to_at_least_one(self):
        """A near-expired token at logout could compute a <=0 remaining
        TTL -- SETEX rejects a non-positive TTL, so this must clamp."""
        from src.core import token_revocation

        mock_client = AsyncMock()
        with patch.object(token_revocation.settings, "REDIS_URL", "redis://redis:6379"):
            with patch.object(token_revocation, "_get_redis_client", return_value=mock_client):
                await token_revocation.revoke_jti("some-jti", ttl_seconds=-5)
        args, _ = mock_client.setex.call_args
        assert args[1] == 1


class TestIsJtiRevoked:
    @pytest.mark.asyncio
    async def test_false_when_redis_url_empty(self):
        from src.core import token_revocation

        with patch.object(token_revocation.settings, "REDIS_URL", ""):
            with patch.object(token_revocation, "_get_redis_client") as mock_get_client:
                result = await token_revocation.is_jti_revoked("some-jti")
        assert result is False
        mock_get_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_true_when_jti_exists_in_redis(self):
        from src.core import token_revocation

        mock_client = AsyncMock()
        mock_client.exists.return_value = 1
        with patch.object(token_revocation.settings, "REDIS_URL", "redis://redis:6379"):
            with patch.object(token_revocation, "_get_redis_client", return_value=mock_client):
                result = await token_revocation.is_jti_revoked("some-jti")
        assert result is True
        mock_client.exists.assert_called_once_with("revoked_jti:some-jti")

    @pytest.mark.asyncio
    async def test_false_when_jti_not_in_redis(self):
        from src.core import token_revocation

        mock_client = AsyncMock()
        mock_client.exists.return_value = 0
        with patch.object(token_revocation.settings, "REDIS_URL", "redis://redis:6379"):
            with patch.object(token_revocation, "_get_redis_client", return_value=mock_client):
                result = await token_revocation.is_jti_revoked("some-jti")
        assert result is False

    @pytest.mark.asyncio
    async def test_fails_open_and_logs_when_redis_raises(self):
        """A defense-in-depth layer on top of the already-real 24h expiry
        and is_active check -- a transient Redis outage must not turn into
        denying every authenticated request app-wide."""
        from src.core import token_revocation

        mock_client = AsyncMock()
        mock_client.exists.side_effect = ConnectionError("redis unreachable")
        with patch.object(token_revocation.settings, "REDIS_URL", "redis://redis:6379"):
            with patch.object(token_revocation, "_get_redis_client", return_value=mock_client):
                with patch.object(token_revocation.logger, "awarning", new=AsyncMock()) as mock_warn:
                    result = await token_revocation.is_jti_revoked("some-jti")
        assert result is False
        mock_warn.assert_called_once()
