"""Tests for the billing domain (task #238) -- Paystack checkout initiation.

TDD: written before the implementation, per project convention.
"""

import uuid
from datetime import datetime, timezone
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
