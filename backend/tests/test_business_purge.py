"""Tests for the background business-purge job (task #260).

Task #252 shipped the user-facing grace-period deletion request. This is
the other half: once purge_at passes, a scheduled job must actually
anonymize PII. Retention decision made with the user (2026-09-15):
anonymize PII on Business and User, but keep the financial ledger
(sales/expenses/purchase orders) untouched indefinitely.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.auth.models import Business, User, UserRole
from src.core.security import get_password_hash

VALID_PASSWORD = "Str0ng!Pass#99"


def _make_user(**overrides) -> User:
    defaults = dict(
        email="owner@example.com",
        hashed_password=get_password_hash(VALID_PASSWORD),
        full_name="Test Owner",
        is_active=True,
        role=UserRole.OWNER,
        email_verified=True,
    )
    defaults.update(overrides)
    user = User(**defaults)
    if "id" not in overrides:
        user.id = uuid.uuid4()
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    return user


def _make_business(**overrides) -> Business:
    defaults = dict(
        name="Real Traders Ltd",
        currency="NGN",
        phone="+2348000000000",
        tax_number="TIN-123456",
        country="Nigeria",
        state="Lagos",
        city="Ikeja",
    )
    defaults.update(overrides)
    business = Business(**defaults)
    if "id" not in overrides:
        business.id = uuid.uuid4()
    return business


def _scalars_all_result(items):
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = items
    return result_mock


class TestPurgeExpiredBusinessDeletions:
    @pytest.mark.asyncio
    async def test_anonymizes_business_and_users_past_purge_at(self):
        from src.auth.service import purge_expired_business_deletions

        business = _make_business(
            deletion_requested_at=datetime.now(timezone.utc) - timedelta(days=31),
            purge_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        owner = _make_user(
            role=UserRole.OWNER,
            business_id=business.id,
            email="real-owner@example.com",
            full_name="Real Owner",
        )
        original_hashed_password = owner.hashed_password

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_all_result([business]),
                _scalars_all_result([owner]),
            ]
        )
        db.flush = AsyncMock()
        db.add = MagicMock()

        with patch("src.auth.service.record_audit_event") as mock_record:
            mock_record.return_value = AsyncMock()
            purged_ids = await purge_expired_business_deletions(db)

        assert purged_ids == [business.id]

        # Business PII anonymized
        assert business.name != "Real Traders Ltd"
        assert business.phone is None
        assert business.tax_number is None
        assert business.country is None
        assert business.state is None
        assert business.city is None
        assert business.purged_at is not None

        # User PII anonymized, password invalidated, login disabled
        assert owner.email != "real-owner@example.com"
        assert owner.full_name != "Real Owner"
        assert owner.hashed_password != original_hashed_password
        assert owner.is_active is False

        # Audit event recorded, using the still-real actor id before it was anonymized
        mock_record.assert_called_once()
        _, kwargs = mock_record.call_args
        assert kwargs["business_id"] == business.id
        assert kwargs["actor_user_id"] == owner.id
        assert kwargs["action"] == "business_purged"
        assert kwargs["entity_type"] == "business"
        assert kwargs["entity_id"] == business.id

    @pytest.mark.asyncio
    async def test_no_businesses_past_purge_at_returns_empty_list(self):
        """Error/edge case: the query itself scopes to purge_at <= now AND
        purged_at IS NULL, so a business not yet due (or already purged)
        must never be touched -- verified here via an empty result set,
        which must produce zero side effects."""
        from src.auth.service import purge_expired_business_deletions

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalars_all_result([]))
        db.flush = AsyncMock()
        db.add = MagicMock()

        with patch("src.auth.service.record_audit_event") as mock_record:
            purged_ids = await purge_expired_business_deletions(db)

        assert purged_ids == []
        mock_record.assert_not_called()
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_query_financial_ledger_tables(self):
        """The retention decision keeps sales/expenses/purchase orders
        indefinitely -- the purge job must never touch them."""
        from src.auth.service import purge_expired_business_deletions

        business = _make_business(
            deletion_requested_at=datetime.now(timezone.utc) - timedelta(days=31),
            purge_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        owner = _make_user(role=UserRole.OWNER, business_id=business.id)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _scalars_all_result([business]),
                _scalars_all_result([owner]),
            ]
        )
        db.flush = AsyncMock()
        db.add = MagicMock()

        with patch("src.auth.service.record_audit_event") as mock_record:
            mock_record.return_value = AsyncMock()
            await purge_expired_business_deletions(db)

        ledger_tables = ("sales", "expenses", "purchase_orders")
        for call in db.execute.call_args_list:
            statement_repr = str(call.args[0]).lower()
            assert not any(t in statement_repr for t in ledger_tables)
