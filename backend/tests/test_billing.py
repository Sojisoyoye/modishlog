"""Tests for the billing domain -- Paystack checkout initiation (task #238)
and idempotent webhook handling (task #239).

TDD: written before the implementation, per project convention.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx as httpx_mod
import pytest
from fastapi.testclient import TestClient

from src.auth.models import Business, SubscriptionStatus, SubscriptionTier, User, UserRole
from src.billing.exceptions import (
    BillingNotConfiguredError,
    BusinessOwnerNotFoundError,
    InvalidTierError,
    PaystackAPIError,
)
from src.core.security import get_password_hash

VALID_PASSWORD = "SuperSecret123!"


def _make_business(**overrides):
    defaults = dict(name="Test Business", currency="NGN")
    defaults.update(overrides)
    business = Business(**defaults)
    business.id = overrides.get("id", uuid.uuid4())
    business.subscription_status = SubscriptionStatus.TRIALING
    business.subscription_tier = SubscriptionTier.PRO
    business.paystack_customer_code = overrides.get("paystack_customer_code")
    return business


def _make_owner(business_id, **overrides):
    defaults = dict(
        email="owner@example.com",
        hashed_password=get_password_hash(VALID_PASSWORD),
        full_name="Business Owner",
        is_active=True,
        role=UserRole.OWNER,
        business_id=business_id,
    )
    defaults.update(overrides)
    user = User(**defaults)
    user.id = overrides.get("id", uuid.uuid4())
    return user


def _mock_client(response_json: dict, status_code: int = 200):
    mock_response = MagicMock()
    mock_response.json.return_value = response_json
    if status_code >= 400:
        mock_response.raise_for_status.side_effect = httpx_mod.HTTPStatusError(
            f"{status_code} error", request=MagicMock(), response=MagicMock(status_code=status_code)
        )
    else:
        mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)
    return mock_client


class TestPaystackClientCreateCustomer:
    @pytest.mark.asyncio
    async def test_create_customer_returns_customer_code(self):
        from src.billing.paystack_client import create_customer

        mock_client = _mock_client({"status": True, "data": {"customer_code": "CUS_abc123"}})
        with patch("src.billing.paystack_client.httpx.AsyncClient", return_value=mock_client):
            with patch("src.billing.paystack_client.settings") as mock_settings:
                mock_settings.PAYSTACK_SECRET_KEY = "sk_test_xxx"
                code = await create_customer("owner@example.com")
        assert code == "CUS_abc123"

    @pytest.mark.asyncio
    async def test_create_customer_raises_on_api_failure(self):
        from src.billing.paystack_client import create_customer

        mock_client = _mock_client({"status": False, "message": "bad request"}, status_code=400)
        with patch("src.billing.paystack_client.httpx.AsyncClient", return_value=mock_client):
            with patch("src.billing.paystack_client.settings") as mock_settings:
                mock_settings.PAYSTACK_SECRET_KEY = "sk_test_xxx"
                with pytest.raises(PaystackAPIError):
                    await create_customer("owner@example.com")


class TestPaystackClientInitializeTransaction:
    @pytest.mark.asyncio
    async def test_initialize_transaction_returns_checkout_data(self):
        from src.billing.paystack_client import initialize_transaction

        mock_client = _mock_client({
            "status": True,
            "data": {
                "authorization_url": "https://checkout.paystack.com/abc123",
                "access_code": "abc123",
                "reference": "ref_xyz",
            },
        })
        with patch("src.billing.paystack_client.httpx.AsyncClient", return_value=mock_client):
            with patch("src.billing.paystack_client.settings") as mock_settings:
                mock_settings.PAYSTACK_SECRET_KEY = "sk_test_xxx"
                result = await initialize_transaction(
                    "owner@example.com", "PLN_basic", "http://localhost:4200/settings/billing"
                )
        assert result["authorization_url"] == "https://checkout.paystack.com/abc123"
        assert result["reference"] == "ref_xyz"

    @pytest.mark.asyncio
    async def test_initialize_transaction_raises_on_network_error(self):
        from src.billing.paystack_client import initialize_transaction

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx_mod.RequestError("timeout"))

        with patch("src.billing.paystack_client.httpx.AsyncClient", return_value=mock_client):
            with patch("src.billing.paystack_client.settings") as mock_settings:
                mock_settings.PAYSTACK_SECRET_KEY = "sk_test_xxx"
                with pytest.raises(PaystackAPIError):
                    await initialize_transaction(
                        "owner@example.com", "PLN_basic", "http://localhost:4200/settings/billing"
                    )


class TestInitiateCheckoutService:
    @pytest.mark.asyncio
    async def test_invalid_tier_raises(self):
        from src.billing.service import initiate_checkout

        db = AsyncMock()
        with pytest.raises(InvalidTierError):
            await initiate_checkout(db, uuid.uuid4(), tier="enterprise")

    @pytest.mark.asyncio
    async def test_missing_plan_code_raises_billing_not_configured(self):
        from src.billing.service import initiate_checkout

        db = AsyncMock()
        with patch("src.billing.service.settings") as mock_settings:
            mock_settings.PAYSTACK_BASIC_PLAN_CODE = ""
            mock_settings.PAYSTACK_PRO_PLAN_CODE = ""
            with pytest.raises(BillingNotConfiguredError):
                await initiate_checkout(db, uuid.uuid4(), tier="basic")

    @pytest.mark.asyncio
    async def test_creates_customer_when_none_exists_yet(self):
        from src.billing.service import initiate_checkout

        business_id = uuid.uuid4()
        business = _make_business(id=business_id, paystack_customer_code=None)
        owner = _make_owner(business_id)

        business_result = MagicMock()
        business_result.scalar_one_or_none.return_value = business
        owner_result = MagicMock()
        owner_result.scalar_one_or_none.return_value = owner

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[business_result, owner_result])
        db.flush = AsyncMock()

        with patch("src.billing.service.settings") as mock_settings:
            mock_settings.PAYSTACK_BASIC_PLAN_CODE = "PLN_basic"
            mock_settings.PAYSTACK_PRO_PLAN_CODE = "PLN_pro"
            mock_settings.FRONTEND_URL = "http://localhost:4200"
            with patch(
                "src.billing.service.create_customer", new=AsyncMock(return_value="CUS_new123")
            ) as mock_create_customer:
                with patch(
                    "src.billing.service.initialize_transaction",
                    new=AsyncMock(return_value={
                        "authorization_url": "https://checkout.paystack.com/xyz",
                        "access_code": "xyz",
                        "reference": "ref_1",
                    }),
                ):
                    result = await initiate_checkout(db, business_id, tier="basic")

        mock_create_customer.assert_called_once_with(owner.email)
        assert business.paystack_customer_code == "CUS_new123"
        assert result["authorization_url"] == "https://checkout.paystack.com/xyz"
        # Checkout initiation alone must never flip subscription state --
        # only task #239's webhook confirmation does that.
        assert business.subscription_status == SubscriptionStatus.TRIALING

    @pytest.mark.asyncio
    async def test_reuses_existing_customer_code(self):
        from src.billing.service import initiate_checkout

        business_id = uuid.uuid4()
        business = _make_business(id=business_id, paystack_customer_code="CUS_existing")
        owner = _make_owner(business_id)

        business_result = MagicMock()
        business_result.scalar_one_or_none.return_value = business
        owner_result = MagicMock()
        owner_result.scalar_one_or_none.return_value = owner

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[business_result, owner_result])
        db.flush = AsyncMock()

        with patch("src.billing.service.settings") as mock_settings:
            mock_settings.PAYSTACK_BASIC_PLAN_CODE = "PLN_basic"
            mock_settings.PAYSTACK_PRO_PLAN_CODE = "PLN_pro"
            mock_settings.FRONTEND_URL = "http://localhost:4200"
            with patch(
                "src.billing.service.create_customer", new=AsyncMock()
            ) as mock_create_customer:
                with patch(
                    "src.billing.service.initialize_transaction",
                    new=AsyncMock(return_value={
                        "authorization_url": "https://checkout.paystack.com/xyz",
                        "access_code": "xyz",
                        "reference": "ref_1",
                    }),
                ):
                    await initiate_checkout(db, business_id, tier="basic")

        mock_create_customer.assert_not_called()
        assert business.paystack_customer_code == "CUS_existing"

    @pytest.mark.asyncio
    async def test_no_owner_user_raises(self):
        from src.billing.service import initiate_checkout

        business_id = uuid.uuid4()
        business = _make_business(id=business_id, paystack_customer_code=None)

        business_result = MagicMock()
        business_result.scalar_one_or_none.return_value = business
        owner_result = MagicMock()
        owner_result.scalar_one_or_none.return_value = None

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[business_result, owner_result])

        with patch("src.billing.service.settings") as mock_settings:
            mock_settings.PAYSTACK_BASIC_PLAN_CODE = "PLN_basic"
            mock_settings.PAYSTACK_PRO_PLAN_CODE = "PLN_pro"
            with pytest.raises(BusinessOwnerNotFoundError):
                await initiate_checkout(db, business_id, tier="basic")


class TestCheckoutEndpoint:
    @pytest.fixture(autouse=True)
    def _setup_client(self):
        from src.main import app

        self.app = app
        self._original_overrides = app.dependency_overrides.copy()
        yield
        app.dependency_overrides = self._original_overrides

    def _override_db(self, db_mock):
        from src.core.database import get_db

        async def _fake_db():
            yield db_mock

        self.app.dependency_overrides[get_db] = _fake_db

    def _override_auth_as(self, role: UserRole):
        from src.auth.dependencies import get_current_active_user, get_current_business_id

        business_id = uuid.uuid4()
        user = MagicMock()
        user.id = uuid.uuid4()
        user.role = role
        user.business_id = business_id
        user.is_active = True

        async def _fake_auth():
            return user

        async def _fake_business_id():
            return business_id

        self.app.dependency_overrides[get_current_active_user] = _fake_auth
        self.app.dependency_overrides[get_current_business_id] = _fake_business_id
        return business_id

    def test_sales_manager_cannot_initiate_checkout(self):
        self._override_db(AsyncMock())
        self._override_auth_as(UserRole.SALES_MANAGER)

        with TestClient(self.app) as client:
            resp = client.post("/api/v1/billing/checkout", json={"tier": "basic"})
        assert resp.status_code == 403

    def test_admin_can_initiate_checkout(self):
        business_id = self._override_auth_as(UserRole.ADMIN)
        business = _make_business(id=business_id, paystack_customer_code="CUS_existing")
        owner = _make_owner(business_id)

        business_result = MagicMock()
        business_result.scalar_one_or_none.return_value = business
        owner_result = MagicMock()
        owner_result.scalar_one_or_none.return_value = owner

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[business_result, owner_result])
        db.flush = AsyncMock()
        self._override_db(db)

        with patch("src.billing.service.settings") as mock_settings:
            mock_settings.PAYSTACK_BASIC_PLAN_CODE = "PLN_basic"
            mock_settings.PAYSTACK_PRO_PLAN_CODE = "PLN_pro"
            mock_settings.FRONTEND_URL = "http://localhost:4200"
            with patch(
                "src.billing.service.initialize_transaction",
                new=AsyncMock(return_value={
                    "authorization_url": "https://checkout.paystack.com/xyz",
                    "access_code": "xyz",
                    "reference": "ref_1",
                }),
            ):
                with TestClient(self.app) as client:
                    resp = client.post("/api/v1/billing/checkout", json={"tier": "basic"})

        assert resp.status_code == 200
        assert resp.json()["authorization_url"] == "https://checkout.paystack.com/xyz"


# ---------------------------------------------------------------------------
# Webhook handling (task #239)
# ---------------------------------------------------------------------------


class TestVerifySignature:
    def test_valid_signature_accepted(self):
        import hashlib
        import hmac

        from src.billing.paystack_client import verify_signature

        with patch("src.billing.paystack_client.settings") as mock_settings:
            mock_settings.PAYSTACK_SECRET_KEY = "sk_test_xxx"
            body = b'{"event": "charge.success"}'
            sig = hmac.new(b"sk_test_xxx", body, hashlib.sha512).hexdigest()
            assert verify_signature(body, sig) is True

    def test_wrong_signature_rejected(self):
        from src.billing.paystack_client import verify_signature

        with patch("src.billing.paystack_client.settings") as mock_settings:
            mock_settings.PAYSTACK_SECRET_KEY = "sk_test_xxx"
            assert verify_signature(b'{"event": "charge.success"}', "not-the-real-signature") is False

    def test_missing_signature_rejected(self):
        from src.billing.paystack_client import verify_signature

        with patch("src.billing.paystack_client.settings") as mock_settings:
            mock_settings.PAYSTACK_SECRET_KEY = "sk_test_xxx"
            assert verify_signature(b'{"event": "charge.success"}', None) is False

    def test_no_secret_configured_rejected(self):
        """Never accept a webhook if billing isn't even configured -- an
        empty secret key must not become a de-facto 'accept anything'."""
        from src.billing.paystack_client import verify_signature

        with patch("src.billing.paystack_client.settings") as mock_settings:
            mock_settings.PAYSTACK_SECRET_KEY = ""
            assert verify_signature(b'{"event": "charge.success"}', "anything") is False


def _mock_execute_sequence(*results):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=list(results))
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _no_match_result():
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    return r


def _match_result(obj):
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


class TestProcessWebhookEvent:
    @pytest.mark.asyncio
    async def test_duplicate_event_is_a_noop(self):
        """Idempotent replay: a WebhookEvent already existing for this key
        means the event was already fully processed -- must not process
        it again (no business mutation, no second audit event)."""
        from src.billing.service import process_webhook_event

        existing_event = MagicMock()
        db = _mock_execute_sequence(_match_result(existing_event))

        await process_webhook_event(
            db, "charge.success", {"id": 123, "customer": {"customer_code": "CUS_1"}}, b"{}"
        )

        # Only the idempotency check ran -- no business lookup attempted.
        assert db.execute.call_count == 1
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_customer_skipped_gracefully(self):
        """A webhook for a customer_code this app doesn't recognize must
        not crash -- log and skip."""
        from src.billing.service import process_webhook_event

        db = _mock_execute_sequence(_no_match_result(), _no_match_result())

        await process_webhook_event(
            db, "charge.success", {"id": 123, "customer": {"customer_code": "CUS_unknown"}}, b"{}"
        )

        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_charge_success_activates_subscription(self):
        from src.billing.service import process_webhook_event

        business_id = uuid.uuid4()
        business = _make_business(id=business_id, paystack_customer_code="CUS_1")
        business.subscription_status = SubscriptionStatus.PAST_DUE
        business.past_due_since = datetime.now(timezone.utc)
        owner = _make_owner(business_id)

        db = _mock_execute_sequence(
            _no_match_result(),  # idempotency check
            _match_result(business),  # business lookup
            _match_result(owner),  # owner lookup for audit
        )

        await process_webhook_event(
            db, "charge.success", {"id": 999, "customer": {"customer_code": "CUS_1"}}, b"{}"
        )

        assert business.subscription_status == SubscriptionStatus.ACTIVE
        assert business.past_due_since is None
        db.add.assert_called()  # the WebhookEvent row was persisted

    @pytest.mark.asyncio
    async def test_payment_failed_sets_past_due_and_timestamp(self):
        from src.billing.service import process_webhook_event

        business_id = uuid.uuid4()
        business = _make_business(id=business_id, paystack_customer_code="CUS_1")
        business.subscription_status = SubscriptionStatus.ACTIVE
        business.past_due_since = None
        owner = _make_owner(business_id)

        db = _mock_execute_sequence(
            _no_match_result(), _match_result(business), _match_result(owner)
        )

        await process_webhook_event(
            db, "invoice.payment_failed", {"id": 1, "customer": {"customer_code": "CUS_1"}}, b"{}"
        )

        assert business.subscription_status == SubscriptionStatus.PAST_DUE
        assert business.past_due_since is not None

    @pytest.mark.asyncio
    async def test_second_payment_failure_does_not_reset_grace_clock(self):
        """A second consecutive failure notification must not push the
        grace-period deadline back out -- the clock starts at the FIRST
        failure."""
        from src.billing.service import process_webhook_event

        business_id = uuid.uuid4()
        first_failure = datetime(2026, 1, 1, tzinfo=timezone.utc)
        business = _make_business(id=business_id, paystack_customer_code="CUS_1")
        business.subscription_status = SubscriptionStatus.PAST_DUE
        business.past_due_since = first_failure
        owner = _make_owner(business_id)

        db = _mock_execute_sequence(
            _no_match_result(), _match_result(business), _match_result(owner)
        )

        await process_webhook_event(
            db, "invoice.payment_failed", {"id": 2, "customer": {"customer_code": "CUS_1"}}, b"{}"
        )

        assert business.past_due_since == first_failure

    @pytest.mark.asyncio
    async def test_subscription_disable_cancels(self):
        from src.billing.service import process_webhook_event

        business_id = uuid.uuid4()
        business = _make_business(id=business_id, paystack_customer_code="CUS_1")
        business.subscription_status = SubscriptionStatus.ACTIVE
        owner = _make_owner(business_id)

        db = _mock_execute_sequence(
            _no_match_result(), _match_result(business), _match_result(owner)
        )

        await process_webhook_event(
            db,
            "subscription.disable",
            {"subscription_code": "SUB_1", "customer": {"customer_code": "CUS_1"}},
            b"{}",
        )

        assert business.subscription_status == SubscriptionStatus.CANCELED

    @pytest.mark.asyncio
    async def test_subscription_create_persists_subscription_code(self):
        from src.billing.service import process_webhook_event

        business_id = uuid.uuid4()
        business = _make_business(id=business_id, paystack_customer_code="CUS_1")
        owner = _make_owner(business_id)

        db = _mock_execute_sequence(
            _no_match_result(), _match_result(business), _match_result(owner)
        )

        await process_webhook_event(
            db,
            "subscription.create",
            {
                "subscription_code": "SUB_new",
                "customer": {"customer_code": "CUS_1"},
                "next_payment_date": "2026-10-01T00:00:00.000Z",
            },
            b"{}",
        )

        assert business.paystack_subscription_code == "SUB_new"
        assert business.subscription_status == SubscriptionStatus.ACTIVE


class TestWebhookEndpoint:
    @pytest.fixture(autouse=True)
    def _setup_client(self):
        from src.main import app

        self.app = app
        self._original_overrides = app.dependency_overrides.copy()
        yield
        app.dependency_overrides = self._original_overrides

    def _override_db(self, db_mock):
        from src.core.database import get_db

        async def _fake_db():
            yield db_mock

        self.app.dependency_overrides[get_db] = _fake_db

    def test_invalid_signature_rejected_without_processing(self):
        self._override_db(AsyncMock())
        with patch("src.billing.router.verify_signature", return_value=False):
            with patch(
                "src.billing.router.process_webhook_event", new=AsyncMock()
            ) as mock_process:
                with TestClient(self.app) as client:
                    resp = client.post(
                        "/api/v1/billing/webhook",
                        json={"event": "charge.success", "data": {}},
                        headers={"x-paystack-signature": "bad"},
                    )
        assert resp.status_code == 401
        mock_process.assert_not_called()

    def test_valid_signature_processes_event(self):
        self._override_db(AsyncMock())
        with patch("src.billing.router.verify_signature", return_value=True):
            with patch(
                "src.billing.router.process_webhook_event", new=AsyncMock()
            ) as mock_process:
                with TestClient(self.app) as client:
                    resp = client.post(
                        "/api/v1/billing/webhook",
                        json={"event": "charge.success", "data": {"id": 1}},
                        headers={"x-paystack-signature": "good"},
                    )
        assert resp.status_code == 200
        mock_process.assert_called_once()


class TestCheckExpiredGracePeriods:
    @pytest.mark.asyncio
    async def test_past_due_over_3_days_moves_to_read_only(self):
        from src.billing.service import check_expired_grace_periods

        business = _make_business(paystack_customer_code="CUS_1")
        business.subscription_status = SubscriptionStatus.PAST_DUE
        business.past_due_since = datetime.now(timezone.utc) - timedelta(days=4)

        result = MagicMock()
        result.scalars.return_value.all.return_value = [business]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)
        db.flush = AsyncMock()

        ids = await check_expired_grace_periods(db)

        assert business.subscription_status == SubscriptionStatus.READ_ONLY
        assert business.id in ids

    @pytest.mark.asyncio
    async def test_query_filters_by_past_due_status_and_cutoff(self):
        """The query itself must scope to PAST_DUE businesses whose grace
        period has actually expired -- not touch every business."""
        from src.billing.service import check_expired_grace_periods

        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)

        await check_expired_grace_periods(db)

        query = db.execute.call_args.args[0]
        compiled = str(query.compile(compile_kwargs={"literal_binds": False}))
        assert "businesses.subscription_status" in compiled
        assert "businesses.past_due_since" in compiled
