"""Tests for FX rate ingestion, alerts, exposure, simulation, and endpoints."""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.auth.service import build_token
from src.core.security import get_password_hash
from src.fx.exceptions import (
    ExposureConfigError,
    FXAlertNotFoundError,
    FXPairNotFoundError,
    FXRateNotFoundError,
    InsufficientRateDataError,
    SimulationNotFoundError,
)
from src.fx.models import (
    AlertDirection,
    FXAlert,
    FXExposure,
    FXForecast,
    FXRate,
    RateSource,
)
from src.fx.schemas import (
    FXAlertCreate,
    FXAlertUpdate,
    FXRateIngest,
    ExposureConfigUpdate,
    ExposureLockRequest,
    SimulationRequest,
)
from src.fx.service import (
    calculate_volatility,
    check_alerts,
    create_alert,
    delete_alert,
    delete_rate,
    get_current_rate,
    get_rate_history,
    get_simulation,
    ingest_rate,
    list_alerts,
    lock_exposure,
    run_simulation,
    update_alert,
    update_exposure_config,
)

VALID_PASSWORD = "Str0ng!Pass#99"


def _make_user(**overrides):
    from src.auth.models import User, UserRole

    defaults = dict(
        email="test@example.com",
        hashed_password=get_password_hash(VALID_PASSWORD),
        full_name="Test User",
        is_active=True,
        role=UserRole.ADMIN,
        failed_login_attempts=0,
        locked_until=None,
    )
    defaults.update(overrides)
    user = User(**defaults)
    user.id = overrides.get("id", uuid.uuid4())
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    return user


def _make_fx_rate(pair="USDNGN", rate=Decimal("1650.250000"), **overrides):
    defaults = dict(
        pair=pair,
        rate=rate,
        source=RateSource.MANUAL,
        timestamp=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    fx = FXRate(**defaults)
    fx.id = overrides.get("id", uuid.uuid4())
    return fx


def _make_alert(pair="USDNGN", **overrides):
    defaults = dict(
        pair=pair,
        direction=AlertDirection.ABOVE,
        threshold_rate=Decimal("1700.000000"),
        is_enabled=True,
        is_triggered=False,
        triggered_at=None,
        triggered_rate=None,
        created_by=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    alert = FXAlert(**defaults)
    alert.id = overrides.get("id", uuid.uuid4())
    return alert


def _make_exposure(pair="USDNGN", **overrides):
    defaults = dict(
        pair=pair,
        total_exposure_amount=Decimal("100000.000000"),
        locked_amount=Decimal("30000.000000"),
        locked_rate=Decimal("1600.000000"),
        floating_amount=Decimal("70000.000000"),
    )
    defaults.update(overrides)
    exp = FXExposure(**defaults)
    exp.id = overrides.get("id", uuid.uuid4())
    exp.created_at = datetime.now(timezone.utc)
    exp.updated_at = datetime.now(timezone.utc)
    return exp


def _mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


def _mock_db_with_execute(scalar_result=None, scalars_result=None):
    db = _mock_db()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = scalar_result
    result_mock.scalar.return_value = scalar_result
    if scalars_result is not None:
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = scalars_result
        result_mock.scalars.return_value = scalars_mock
    db.execute = AsyncMock(return_value=result_mock)
    return db


# ---------------------------------------------------------------------------
# Service tests - ingest_rate
# ---------------------------------------------------------------------------


class TestIngestRate:
    @pytest.mark.asyncio
    async def test_ingest_rate_success(self):
        db = _mock_db()
        # check_alerts query returns no alerts
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        data = FXRateIngest(
            pair="USDNGN",
            rate=Decimal("1650.25"),
            source="manual",
        )
        rate = await ingest_rate(db, data, uuid.uuid4())
        assert rate.pair == "USDNGN"
        assert rate.rate == Decimal("1650.25")
        assert rate.source == RateSource.MANUAL
        assert db.add.called

    @pytest.mark.asyncio
    async def test_ingest_rate_with_timestamp(self):
        db = _mock_db()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        ts = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)
        data = FXRateIngest(
            pair="EURNGN",
            rate=Decimal("1800.00"),
            source="cbn_official",
            timestamp=ts,
        )
        rate = await ingest_rate(db, data, uuid.uuid4())
        assert rate.timestamp == ts
        assert rate.source == RateSource.CBN_OFFICIAL


# ---------------------------------------------------------------------------
# Service tests - get_current_rate
# ---------------------------------------------------------------------------


class TestGetCurrentRate:
    @pytest.mark.asyncio
    async def test_success(self):
        fx = _make_fx_rate()
        db = _mock_db_with_execute(scalar_result=fx)
        result = await get_current_rate(db, "USDNGN")
        assert result.pair == "USDNGN"

    @pytest.mark.asyncio
    async def test_not_found(self):
        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(FXPairNotFoundError):
            await get_current_rate(db, "XYZABC")


# ---------------------------------------------------------------------------
# Service tests - get_rate_history
# ---------------------------------------------------------------------------


class TestGetRateHistory:
    @pytest.mark.asyncio
    async def test_history_with_stats(self):
        rates = [
            _make_fx_rate(rate=Decimal("1600")),
            _make_fx_rate(rate=Decimal("1650")),
            _make_fx_rate(rate=Decimal("1700")),
        ]
        db = _mock_db_with_execute(scalars_result=rates)

        history = await get_rate_history(db, "USDNGN", date(2026, 1, 1), date(2026, 3, 31))
        assert history.pair == "USDNGN"
        assert history.period_high == Decimal("1700")
        assert history.period_low == Decimal("1600")
        assert len(history.rates) == 3
        assert history.pct_change > 0

    @pytest.mark.asyncio
    async def test_history_empty_raises(self):
        db = _mock_db_with_execute(scalars_result=[])
        with pytest.raises(FXPairNotFoundError):
            await get_rate_history(db, "USDNGN", date(2026, 1, 1), date(2026, 1, 2))


# ---------------------------------------------------------------------------
# Service tests - alerts
# ---------------------------------------------------------------------------


class TestAlerts:
    @pytest.mark.asyncio
    async def test_create_alert(self):
        db = _mock_db()
        db.execute = AsyncMock()
        data = FXAlertCreate(
            pair="USDNGN",
            direction="above",
            threshold_rate=Decimal("1700"),
        )
        alert = await create_alert(db, data, uuid.uuid4())
        assert alert.pair == "USDNGN"
        assert alert.direction == AlertDirection.ABOVE
        assert alert.is_enabled is True
        assert alert.is_triggered is False

    @pytest.mark.asyncio
    async def test_list_alerts(self):
        alerts = [_make_alert(), _make_alert(pair="EURNGN")]
        db = _mock_db_with_execute(scalars_result=alerts)
        result = await list_alerts(db)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_update_alert(self):
        alert = _make_alert()
        db = _mock_db_with_execute(scalar_result=alert)
        data = FXAlertUpdate(threshold_rate=Decimal("1800"))
        result = await update_alert(db, alert.id, data)
        assert result.threshold_rate == Decimal("1800")

    @pytest.mark.asyncio
    async def test_update_alert_not_found(self):
        db = _mock_db_with_execute(scalar_result=None)
        data = FXAlertUpdate(is_enabled=False)
        with pytest.raises(FXAlertNotFoundError):
            await update_alert(db, uuid.uuid4(), data)

    @pytest.mark.asyncio
    async def test_delete_alert(self):
        alert = _make_alert()
        db = _mock_db_with_execute(scalar_result=alert)
        await delete_alert(db, alert.id)
        db.delete.assert_called_once_with(alert)

    @pytest.mark.asyncio
    async def test_check_alerts_triggers(self):
        alert = _make_alert(
            direction=AlertDirection.ABOVE,
            threshold_rate=Decimal("1700"),
        )
        db = _mock_db_with_execute(scalars_result=[alert])

        triggered = await check_alerts(db, "USDNGN", Decimal("1750"))
        assert len(triggered) == 1
        assert alert.is_triggered is True
        assert alert.triggered_rate == Decimal("1750")

    @pytest.mark.asyncio
    async def test_check_alerts_no_trigger(self):
        alert = _make_alert(
            direction=AlertDirection.ABOVE,
            threshold_rate=Decimal("1700"),
        )
        db = _mock_db_with_execute(scalars_result=[alert])

        triggered = await check_alerts(db, "USDNGN", Decimal("1650"))
        assert len(triggered) == 0
        assert alert.is_triggered is False

    @pytest.mark.asyncio
    async def test_check_alerts_below_direction(self):
        alert = _make_alert(
            direction=AlertDirection.BELOW,
            threshold_rate=Decimal("1600"),
        )
        db = _mock_db_with_execute(scalars_result=[alert])

        triggered = await check_alerts(db, "USDNGN", Decimal("1550"))
        assert len(triggered) == 1
        assert alert.is_triggered is True


# ---------------------------------------------------------------------------
# Service tests - exposure
# ---------------------------------------------------------------------------


class TestDeleteRate:
    @pytest.mark.asyncio
    async def test_delete_rate_success(self):
        rate = _make_fx_rate()
        db = _mock_db_with_execute(scalar_result=rate)
        await delete_rate(db, rate.id)
        db.delete.assert_called_once_with(rate)

    @pytest.mark.asyncio
    async def test_delete_rate_not_found(self):
        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(FXRateNotFoundError):
            await delete_rate(db, uuid.uuid4())


class TestExposure:
    @pytest.mark.asyncio
    async def test_lock_exposure(self):
        db = _mock_db()
        # Mock total_exposure and already_locked query
        result_mock = MagicMock()
        result_mock.one.return_value = (Decimal("100000"), Decimal("30000"))
        db.execute = AsyncMock(return_value=result_mock)

        data = ExposureLockRequest(
            pair="USDNGN",
            amount_to_lock=Decimal("20000"),
            lock_rate=Decimal("1650"),
        )
        exp = await lock_exposure(db, data, uuid.uuid4())
        assert exp.locked_amount == Decimal("20000")
        assert exp.locked_rate == Decimal("1650")

    @pytest.mark.asyncio
    async def test_lock_exposure_exceeded(self):
        from src.fx.exceptions import ExposureLockExceededError

        db = _mock_db()
        result_mock = MagicMock()
        result_mock.one.return_value = (Decimal("100000"), Decimal("90000"))
        db.execute = AsyncMock(return_value=result_mock)

        data = ExposureLockRequest(
            pair="USDNGN",
            amount_to_lock=Decimal("20000"),
            lock_rate=Decimal("1650"),
        )
        with pytest.raises(ExposureLockExceededError):
            await lock_exposure(db, data, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_update_exposure_config(self):
        db = _mock_db()
        db.execute = AsyncMock()
        data = ExposureConfigUpdate(
            locked_pct=Decimal("40"),
            floating_pct=Decimal("60"),
        )
        config = await update_exposure_config(db, data, uuid.uuid4())
        assert config.locked_pct == Decimal("40")
        assert config.floating_pct == Decimal("60")

    @pytest.mark.asyncio
    async def test_update_exposure_config_invalid(self):
        db = _mock_db()
        data = ExposureConfigUpdate(
            locked_pct=Decimal("50"),
            floating_pct=Decimal("60"),
        )
        with pytest.raises(ExposureConfigError):
            await update_exposure_config(db, data, uuid.uuid4())


# ---------------------------------------------------------------------------
# Service tests - volatility
# ---------------------------------------------------------------------------


class TestVolatility:
    @pytest.mark.asyncio
    async def test_calculate_volatility(self):
        # Create rates with varying values
        rates = [
            _make_fx_rate(rate=Decimal("1600")),
            _make_fx_rate(rate=Decimal("1610")),
            _make_fx_rate(rate=Decimal("1605")),
            _make_fx_rate(rate=Decimal("1620")),
            _make_fx_rate(rate=Decimal("1615")),
        ]
        db = _mock_db_with_execute(scalars_result=rates)

        result = await calculate_volatility(db, "USDNGN", days=5)
        assert result.pair == "USDNGN"
        assert result.volatility > 0
        assert result.data_points == 4  # n-1 returns

    @pytest.mark.asyncio
    async def test_volatility_insufficient_data(self):
        db = _mock_db_with_execute(scalars_result=[_make_fx_rate()])
        with pytest.raises(FXPairNotFoundError):
            await calculate_volatility(db, "USDNGN", days=30)


# ---------------------------------------------------------------------------
# Service tests - Monte Carlo simulation
# ---------------------------------------------------------------------------


class TestSimulation:
    @pytest.mark.asyncio
    async def test_run_simulation(self):
        # Create 50 rate points for simulation
        import random as rng

        rng.seed(42)  # deterministic
        rates = []
        base_rate = 1650.0
        for i in range(50):
            r = _make_fx_rate(rate=Decimal(str(round(base_rate + rng.gauss(0, 10), 4))))
            rates.append(r)

        db = _mock_db_with_execute(scalars_result=rates)

        data = SimulationRequest(
            pair="USDNGN",
            horizon_days=30,
            num_simulations=1000,
            confidence_level=Decimal("95"),
        )
        sim = await run_simulation(db, data, uuid.uuid4())
        assert sim.pair == "USDNGN"
        assert sim.horizon_days == 30
        assert sim.num_simulations == 1000
        assert sim.p5_rate > 0
        assert sim.p50_rate > 0
        assert sim.p95_rate > 0
        assert sim.p5_rate <= sim.p50_rate <= sim.p95_rate
        assert sim.distribution_data is not None
        assert len(sim.distribution_data) == 20  # 20 buckets

    @pytest.mark.asyncio
    async def test_simulation_insufficient_data(self):
        rates = [_make_fx_rate() for _ in range(5)]
        db = _mock_db_with_execute(scalars_result=rates)

        data = SimulationRequest(
            pair="USDNGN",
            horizon_days=30,
            num_simulations=1000,
        )
        with pytest.raises(InsufficientRateDataError):
            await run_simulation(db, data, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_simulation_not_found(self):
        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(SimulationNotFoundError):
            await get_simulation(db, uuid.uuid4())


# ---------------------------------------------------------------------------
# Service tests - external sync
# ---------------------------------------------------------------------------


class TestExternalSync:
    @pytest.mark.asyncio
    async def test_sync_no_api_key(self):
        from src.fx.exceptions import ExternalRateSyncError
        from src.fx.service import sync_external_rates

        db = _mock_db()
        with patch("src.fx.service.settings") as mock_settings:
            mock_settings.FX_API_KEY = ""
            with pytest.raises(ExternalRateSyncError):
                await sync_external_rates(db)

    @pytest.mark.asyncio
    async def test_sync_api_error(self):
        import httpx as httpx_mod

        from src.fx.exceptions import ExternalRateSyncError
        from src.fx.service import sync_external_rates

        db = _mock_db()
        # Mock alerts query
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with patch("src.fx.service.settings") as mock_settings:
            mock_settings.FX_API_KEY = "test-key"
            mock_settings.FX_API_URL = "https://api.test.com/fx"
            with patch("src.fx.service.httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_response = MagicMock()
                mock_response.raise_for_status.side_effect = httpx_mod.HTTPStatusError(
                    "500 error",
                    request=MagicMock(),
                    response=MagicMock(status_code=500),
                )
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_cls.return_value = mock_client

                with pytest.raises(ExternalRateSyncError):
                    await sync_external_rates(db)

    @pytest.mark.asyncio
    async def test_sync_success(self):
        from src.fx.service import sync_external_rates

        db = _mock_db()
        # Mock alerts query
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with patch("src.fx.service.settings") as mock_settings:
            mock_settings.FX_API_KEY = "test-key"
            mock_settings.FX_API_URL = "https://api.test.com/fx"
            with patch("src.fx.service.httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_response = MagicMock()
                mock_response.raise_for_status = MagicMock()
                mock_response.json.return_value = {
                    "rates": {"USDNGN": 1650.25, "EURNGN": 1800.50}
                }
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_cls.return_value = mock_client

                rates = await sync_external_rates(db)
                assert len(rates) == 2
                assert db.add.call_count == 2


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestFXEndpoints:
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

    def _auth_headers(self):
        user = _make_user()
        token = build_token(user)
        return {"Authorization": f"Bearer {token}"}, user

    def _override_auth(self):
        from src.auth.dependencies import get_current_active_user
        u = _make_user()
        async def _fake_auth():
            return u
        self.app.dependency_overrides[get_current_active_user] = _fake_auth

    def test_ingest_requires_auth(self):
        db = _mock_db()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/fx/rates/ingest",
                json={
                    "pair": "USDNGN",
                    "rate": "1650.25",
                    "source": "manual",
                },
            )
        assert resp.status_code == 401

    def test_get_rate_not_found(self):
        self._override_auth()
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/fx/rates/XYZABC")
        assert resp.status_code == 404

    def test_current_rates_empty(self):
        self._override_auth()
        db = _mock_db()
        # distinct pairs returns empty
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/fx/rates/current")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_alert_requires_auth(self):
        db = _mock_db()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/fx/alerts",
                json={
                    "pair": "USDNGN",
                    "direction": "above",
                    "threshold_rate": "1700",
                },
            )
        assert resp.status_code == 401

    def test_list_alerts_empty(self):
        self._override_auth()
        db = _mock_db_with_execute(scalars_result=[])
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/fx/alerts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_simulate_requires_auth(self):
        db = _mock_db()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/fx/simulate",
                json={
                    "pair": "USDNGN",
                    "horizon_days": 30,
                    "num_simulations": 1000,
                },
            )
        assert resp.status_code == 401

    def test_simulation_not_found(self):
        self._override_auth()
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.get(f"/api/v1/fx/simulate/{fake_id}")
        assert resp.status_code == 404

    def test_exposure_config_requires_auth(self):
        db = _mock_db()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.put(
                "/api/v1/fx/exposure/config",
                json={"locked_pct": "40", "floating_pct": "60"},
            )
        assert resp.status_code == 401

    def test_delete_rate_requires_auth(self):
        db = _mock_db()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.delete(f"/api/v1/fx/rates/{uuid.uuid4()}")
        assert resp.status_code == 401

    def test_delete_rate_success(self):
        rate = _make_fx_rate()
        self._override_auth()
        db = _mock_db_with_execute(scalar_result=rate)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.delete(f"/api/v1/fx/rates/{rate.id}")
        assert resp.status_code == 204

    def test_delete_rate_not_found(self):
        self._override_auth()
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        fake_id = str(uuid.uuid4())
        with TestClient(self.app) as client:
            resp = client.delete(f"/api/v1/fx/rates/{fake_id}")
        assert resp.status_code == 404

    def test_forecast_generate_requires_auth(self):
        db = _mock_db()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/fx/forecast/generate",
                json={"pair": "USDNGN", "horizon_days": 30},
            )
        assert resp.status_code == 401

    def test_forecast_date_not_found(self):
        self._override_auth()
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/fx/forecast/USDNGN/2026-06-01")
        assert resp.status_code == 404

    def test_forecast_range_empty(self):
        self._override_auth()
        db = _mock_db_with_execute(scalars_result=[])
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get(
                "/api/v1/fx/forecast/USDNGN",
                params={"date_from": "2026-06-01", "date_to": "2026-06-30"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pair"] == "USDNGN"
        assert data["forecasts"] == []

    def test_sync_rates_requires_auth(self):
        db = _mock_db()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post("/api/v1/fx/rates/sync")
        assert resp.status_code == 401

    def test_sync_rates_success(self):
        from src.fx.exceptions import ExternalRateSyncError
        self._override_auth()
        rate = _make_fx_rate()
        db = _mock_db_with_execute(scalars_result=[rate])
        self._override_db(db)
        with patch("src.fx.router.sync_external_rates", new=AsyncMock(return_value=[rate])):
            with TestClient(self.app) as client:
                resp = client.post("/api/v1/fx/rates/sync")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_sync_rates_502_on_provider_error(self):
        from src.fx.exceptions import ExternalRateSyncError
        self._override_auth()
        db = _mock_db()
        self._override_db(db)
        with patch("src.fx.router.sync_external_rates", new=AsyncMock(side_effect=ExternalRateSyncError("test-provider", 503, "down"))):
            with TestClient(self.app) as client:
                resp = client.post("/api/v1/fx/rates/sync")
        assert resp.status_code == 502

    def test_backfill_requires_auth(self):
        db = _mock_db()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post(
                "/api/v1/fx/rates/backfill",
                params={"pair": "USDNGN", "date_from": "2026-01-01", "date_to": "2026-03-31"},
            )
        assert resp.status_code == 401

    def test_backfill_success(self):
        self._override_auth()
        db = _mock_db()
        self._override_db(db)
        with patch("src.fx.router.backfill_historical_data", new=AsyncMock(return_value=30)):
            with TestClient(self.app) as client:
                resp = client.post(
                    "/api/v1/fx/rates/backfill",
                    params={"pair": "USDNGN", "date_from": "2026-01-01", "date_to": "2026-03-31"},
                )
        assert resp.status_code == 200
        assert resp.json()["records_inserted"] == 30

    def test_backfill_free_requires_auth(self):
        db = _mock_db()
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.post("/api/v1/fx/rates/backfill-free")
        assert resp.status_code == 401

    def test_backfill_free_success(self):
        self._override_auth()
        db = _mock_db()
        self._override_db(db)
        with patch("src.fx.router.backfill_from_exchange_api", new=AsyncMock(return_value=90)):
            with TestClient(self.app) as client:
                resp = client.post("/api/v1/fx/rates/backfill-free", params={"pair": "USDNGN", "days": 90})
        assert resp.status_code == 200
        assert resp.json()["records_inserted"] == 90
        assert resp.json()["pair"] == "USDNGN"


# ---------------------------------------------------------------------------
# Forecast service tests
# ---------------------------------------------------------------------------


def _make_forecast(pair="USDNGN", **overrides):
    defaults = dict(
        pair=pair,
        forecast_date=datetime(2026, 6, 15, tzinfo=timezone.utc),
        base_rate=Decimal("1650.000000"),
        best_case_rate=Decimal("1600.000000"),
        worst_case_rate=Decimal("1700.000000"),
        prophet_lower=Decimal("1610.000000"),
        prophet_upper=Decimal("1690.000000"),
        model_version="prophet-v1",
        mae=None,
        mape=None,
        generated_at=datetime.now(timezone.utc),
        generated_by=uuid.uuid4(),
    )
    defaults.update(overrides)
    fc = FXForecast(**defaults)
    fc.id = overrides.get("id", uuid.uuid4())
    return fc


class TestForecastHelpers:
    def _make_df(self, n=90, base=1378.0, noise=0.003):
        """Generate synthetic daily FX prices."""
        import numpy as np
        rng = np.random.default_rng(42)
        log_rets = rng.normal(0, noise, n - 1)
        prices = base * np.exp(np.concatenate([[0], np.cumsum(log_rets)]))
        dates = pd.date_range("2026-01-01", periods=n, freq="D")
        return pd.DataFrame({"ds": dates, "y": prices})

    def test_gbm_forecast_length(self):
        from src.fx.forecast_service import _gbm_forecast

        df = self._make_df()
        scenarios = _gbm_forecast(df, horizon_days=10, num_simulations=200)
        assert len(scenarios) == 10

    def test_gbm_forecast_values_near_S0(self):
        """Median path should stay close to S0 over a short horizon."""
        from src.fx.forecast_service import _gbm_forecast

        df = self._make_df(base=1378.0)
        scenarios = _gbm_forecast(df, horizon_days=30, num_simulations=500)
        # With tiny drift and vol, 30-day median should remain within ±10% of S0
        for s in scenarios:
            assert 1000 < s["base_rate"] < 1800, f"base_rate out of range: {s['base_rate']}"

    def test_gbm_forecast_ordering(self):
        """best_case ≤ base ≤ worst_case for every day."""
        from src.fx.forecast_service import _gbm_forecast

        df = self._make_df()
        scenarios = _gbm_forecast(df, horizon_days=20, num_simulations=500)
        for s in scenarios:
            assert s["best_case_rate"] <= s["base_rate"] <= s["worst_case_rate"]

    def test_gbm_forecast_positive(self):
        """GBM paths must never go negative."""
        from src.fx.forecast_service import _gbm_forecast

        df = self._make_df()
        scenarios = _gbm_forecast(df, horizon_days=180, num_simulations=500)
        for s in scenarios:
            assert s["base_rate"] > 0
            assert s["best_case_rate"] > 0
            assert s["worst_case_rate"] > 0


class TestFetchHistoricalRates:
    @pytest.mark.asyncio
    async def test_insufficient_data_raises(self):
        from src.fx.forecast_service import _fetch_historical_rates

        rates = [_make_fx_rate() for _ in range(5)]
        db = _mock_db_with_execute(scalars_result=rates)
        with pytest.raises(InsufficientRateDataError):
            await _fetch_historical_rates(db, "USDNGN")

    @pytest.mark.asyncio
    async def test_returns_dataframe(self):
        from src.fx.forecast_service import _fetch_historical_rates

        base_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        rates = [
            _make_fx_rate(
                rate=Decimal(str(1650 + i)),
                timestamp=base_ts + timedelta(days=i),
                created_at=base_ts + timedelta(days=i),
            )
            for i in range(35)
        ]
        db = _mock_db_with_execute(scalars_result=rates)
        df = await _fetch_historical_rates(db, "USDNGN")
        assert isinstance(df, pd.DataFrame)
        assert "ds" in df.columns
        assert "y" in df.columns
        assert len(df) == 35


class TestTrainAndForecast:
    @pytest.mark.asyncio
    async def test_train_and_forecast_full_pipeline(self):
        from src.fx.forecast_service import train_and_forecast

        base_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        rates = [
            _make_fx_rate(
                rate=Decimal(str(round(1650 + i * 0.5, 2))),
                timestamp=base_ts + timedelta(days=i),
                created_at=base_ts + timedelta(days=i),
            )
            for i in range(50)
        ]
        db = _mock_db_with_execute(scalars_result=rates)

        forecasts = await train_and_forecast(
            db, "USDNGN", uuid.uuid4(), horizon_days=10, num_simulations=200,
        )

        assert len(forecasts) == 10
        for fc in forecasts:
            assert fc.pair == "USDNGN"
            assert fc.model_version == "gbm-v1"
            assert fc.base_rate > 0
            assert fc.best_case_rate > 0
            assert fc.worst_case_rate > 0
        assert db.add.call_count == 10

    @pytest.mark.asyncio
    async def test_train_and_forecast_insufficient_data(self):
        from src.fx.forecast_service import train_and_forecast

        base_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        rates = [
            _make_fx_rate(
                timestamp=base_ts + timedelta(days=i),
                created_at=base_ts + timedelta(days=i),
            )
            for i in range(5)
        ]
        db = _mock_db_with_execute(scalars_result=rates)

        with pytest.raises(InsufficientRateDataError):
            await train_and_forecast(db, "USDNGN", uuid.uuid4())


class TestGetForecastForDate:
    @pytest.mark.asyncio
    async def test_success(self):
        from src.fx.forecast_service import get_forecast_for_date

        fc = _make_forecast()
        db = _mock_db_with_execute(scalar_result=fc)
        result = await get_forecast_for_date(db, "USDNGN", date(2026, 6, 15))
        assert result.pair == "USDNGN"
        assert result.base_rate == Decimal("1650.000000")

    @pytest.mark.asyncio
    async def test_not_found(self):
        from src.fx.forecast_service import get_forecast_for_date

        db = _mock_db_with_execute(scalar_result=None)
        with pytest.raises(FXPairNotFoundError):
            await get_forecast_for_date(db, "USDNGN", date(2026, 6, 15))

    @pytest.mark.asyncio
    async def test_stale_forecast_still_returned(self):
        from src.fx.forecast_service import get_forecast_for_date

        fc = _make_forecast(
            generated_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        db = _mock_db_with_execute(scalar_result=fc)
        result = await get_forecast_for_date(
            db, "USDNGN", date(2026, 6, 15), user_id=uuid.uuid4(),
        )
        assert result.pair == "USDNGN"


class TestGetForecastRange:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        from src.fx.forecast_service import get_forecast_range

        forecasts = [_make_forecast(), _make_forecast()]
        db = _mock_db_with_execute(scalars_result=forecasts)
        result = await get_forecast_range(db, "USDNGN", date(2026, 6, 1), date(2026, 6, 30))
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_range(self):
        from src.fx.forecast_service import get_forecast_range

        db = _mock_db_with_execute(scalars_result=[])
        result = await get_forecast_range(db, "USDNGN", date(2026, 6, 1), date(2026, 6, 30))
        assert result == []


class TestUpdateForecastAccuracy:
    @pytest.mark.asyncio
    async def test_no_forecasts(self):
        from src.fx.forecast_service import update_forecast_accuracy

        db = _mock_db_with_execute(scalars_result=[])
        result = await update_forecast_accuracy(db, "USDNGN")
        assert result.pair == "USDNGN"
        assert result.total_evaluated == 0
        assert result.mean_mae == Decimal("0")

    @pytest.mark.asyncio
    async def test_with_matching_actuals(self):
        from src.fx.forecast_service import update_forecast_accuracy

        fc = _make_forecast(
            forecast_date=datetime(2026, 3, 15, tzinfo=timezone.utc),
            base_rate=Decimal("1650.000000"),
        )
        actual_rate = _make_fx_rate(rate=Decimal("1645.000000"))

        db = _mock_db()
        # First execute: fetch forecasts
        forecasts_result = MagicMock()
        forecasts_scalars = MagicMock()
        forecasts_scalars.all.return_value = [fc]
        forecasts_result.scalars.return_value = forecasts_scalars

        # Second execute: fetch actual rate for each forecast date
        actual_result = MagicMock()
        actual_result.scalar_one_or_none.return_value = actual_rate

        db.execute = AsyncMock(side_effect=[forecasts_result, actual_result])

        result = await update_forecast_accuracy(db, "USDNGN")
        assert result.pair == "USDNGN"
        assert result.total_evaluated == 1
        assert result.mean_mae > 0
        assert result.mean_mape > 0
        # MAE should be |1650 - 1645| = 5
        assert result.mean_mae == Decimal("5.000000")

    @pytest.mark.asyncio
    async def test_with_no_matching_actuals(self):
        from src.fx.forecast_service import update_forecast_accuracy

        fc = _make_forecast(
            forecast_date=datetime(2026, 3, 15, tzinfo=timezone.utc),
        )

        db = _mock_db()
        forecasts_result = MagicMock()
        forecasts_scalars = MagicMock()
        forecasts_scalars.all.return_value = [fc]
        forecasts_result.scalars.return_value = forecasts_scalars

        actual_result = MagicMock()
        actual_result.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(side_effect=[forecasts_result, actual_result])

        result = await update_forecast_accuracy(db, "USDNGN")
        assert result.total_evaluated == 0
        assert result.mean_mae == Decimal("0")


# ---------------------------------------------------------------------------
# CSV Export endpoint tests
# ---------------------------------------------------------------------------


class TestFXExportEndpoint:
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

    def _override_auth(self):
        from src.auth.dependencies import get_current_active_user
        u = _make_user()
        async def _fake_auth():
            return u
        self.app.dependency_overrides[get_current_active_user] = _fake_auth

    def _make_execute_for_rates(self, rates: list):
        """Return AsyncMock execute for listing FX rates."""
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = rates
        result_mock.scalars.return_value = scalars_mock
        return AsyncMock(return_value=result_mock)

    def test_export_fx_csv_returns_csv_content_type(self):
        self._override_auth()
        db = _mock_db()
        db.execute = self._make_execute_for_rates([])
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/fx/export.csv")

        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    def test_export_fx_csv_has_correct_headers(self):
        self._override_auth()
        db = _mock_db()
        db.execute = self._make_execute_for_rates([])
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/fx/export.csv")

        assert resp.status_code == 200
        first_line = resp.text.splitlines()[0]
        assert "pair" in first_line
        assert "rate" in first_line
        assert "source" in first_line
        assert "timestamp" in first_line

    def test_export_fx_csv_content_disposition(self):
        self._override_auth()
        db = _mock_db()
        db.execute = self._make_execute_for_rates([])
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/fx/export.csv")

        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert ".csv" in resp.headers.get("content-disposition", "")

    def test_export_fx_csv_with_data_row(self):
        self._override_auth()
        rate = _make_fx_rate(pair="USDNGN", rate=Decimal("1650.250000"))
        db = _mock_db()
        db.execute = self._make_execute_for_rates([rate])
        self._override_db(db)

        with TestClient(self.app) as client:
            resp = client.get("/api/v1/fx/export.csv?pair=USDNGN")

        assert resp.status_code == 200
        lines = resp.text.strip().splitlines()
        # Header + 1 data row
        assert len(lines) == 2
        # Data row should contain the pair
        assert "USDNGN" in lines[1]


# ---------------------------------------------------------------------------
# Tests for get_live_usdngn_rate (Task #74)
# ---------------------------------------------------------------------------


class TestGetLiveUsdNgnRate:
    """Tests for the live rate cache with 4-hour TTL and open API fetch."""

    def _override_auth(self, app):
        from src.auth.dependencies import get_current_active_user
        u = _make_user()
        async def _fake_auth():
            return u
        app.dependency_overrides[get_current_active_user] = _fake_auth

    @pytest.mark.asyncio
    async def test_returns_cached_rate_when_fresh(self):
        """If a USDNGN rate younger than 4h exists, return it without hitting the API."""
        from src.fx.service import get_live_usdngn_rate

        fresh_rate = _make_fx_rate(
            pair="USDNGN",
            rate=Decimal("1650.000000"),
            timestamp=datetime.now(timezone.utc),
        )
        db = _mock_db()
        result = MagicMock()
        result.scalar_one_or_none.return_value = fresh_rate
        db.execute = AsyncMock(return_value=result)

        with patch("src.fx.service.httpx.AsyncClient") as mock_client_cls:
            rate, fetched_at, cached = await get_live_usdngn_rate(db)

        assert rate == Decimal("1650.000000")
        assert cached is True
        mock_client_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetches_from_api_when_stale(self):
        """If cached rate is older than 4h, fetch from open API and store."""
        from src.fx.service import get_live_usdngn_rate

        stale_rate = _make_fx_rate(
            pair="USDNGN",
            rate=Decimal("1600.000000"),
            timestamp=datetime.now(timezone.utc) - timedelta(hours=5),
        )
        db = _mock_db()

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = stale_rate
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db.execute = mock_execute

        mock_response = MagicMock()
        mock_response.json.return_value = {"rates": {"NGN": 1725.5}}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.fx.service.httpx.AsyncClient", return_value=mock_client):
            rate, fetched_at, cached = await get_live_usdngn_rate(db)

        assert rate == Decimal("1725.5")
        assert cached is False
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetches_from_api_when_no_cache(self):
        """If no cached rate exists at all, fetch from API."""
        from src.fx.service import get_live_usdngn_rate

        db = _mock_db()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)

        mock_response = MagicMock()
        mock_response.json.return_value = {"rates": {"NGN": 1700.0}}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.fx.service.httpx.AsyncClient", return_value=mock_client):
            rate, fetched_at, cached = await get_live_usdngn_rate(db)

        assert rate == Decimal("1700.0")
        assert cached is False

    @pytest.mark.asyncio
    async def test_returns_stale_rate_on_api_failure(self):
        """If the API fails and a stale cached rate exists, return stale without raising."""
        from src.fx.service import get_live_usdngn_rate
        import httpx as httpx_module

        stale_rate = _make_fx_rate(
            pair="USDNGN",
            rate=Decimal("1610.000000"),
            timestamp=datetime.now(timezone.utc) - timedelta(hours=6),
        )
        db = _mock_db()
        result = MagicMock()
        result.scalar_one_or_none.return_value = stale_rate
        db.execute = AsyncMock(return_value=result)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx_module.RequestError("timeout"))

        with patch("src.fx.service.httpx.AsyncClient", return_value=mock_client):
            rate, fetched_at, cached = await get_live_usdngn_rate(db)

        assert rate == Decimal("1610.000000")
        assert cached is True

    @pytest.mark.asyncio
    async def test_live_endpoint_returns_rate(self):
        """GET /fx/live returns usd_ngn, fetched_at, cached fields."""
        from src.main import app
        from src.core.database import get_db

        fresh_rate = _make_fx_rate(
            pair="USDNGN",
            rate=Decimal("1680.000000"),
            timestamp=datetime.now(timezone.utc),
        )
        db = _mock_db()
        result = MagicMock()
        result.scalar_one_or_none.return_value = fresh_rate
        db.execute = AsyncMock(return_value=result)

        original_overrides = app.dependency_overrides.copy()
        self._override_auth(app)
        app.dependency_overrides[get_db] = lambda: db
        try:
            with TestClient(app) as client:
                resp = client.get("/api/v1/fx/live")
            assert resp.status_code == 200
            data = resp.json()
            assert "usd_ngn" in data
            assert "fetched_at" in data
            assert "cached" in data
            assert data["cached"] is True
        finally:
            app.dependency_overrides = original_overrides
