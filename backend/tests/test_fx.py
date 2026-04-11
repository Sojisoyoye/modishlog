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
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/fx/rates/XYZABC")
        assert resp.status_code == 404

    def test_current_rates_empty(self):
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
        db = _mock_db_with_execute(scalar_result=None)
        self._override_db(db)
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/fx/forecast/USDNGN/2026-06-01")
        assert resp.status_code == 404

    def test_forecast_range_empty(self):
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
    def test_compute_volatility(self):
        from src.fx.forecast_service import _compute_volatility

        df = pd.DataFrame({"y": [1650.0, 1660.0, 1655.0, 1670.0, 1665.0]})
        vol = _compute_volatility(df)
        assert vol > 0
        assert vol < 1  # FX vol should be small

    def test_compute_volatility_single_point(self):
        from src.fx.forecast_service import _compute_volatility

        df = pd.DataFrame({"y": [1650.0]})
        vol = _compute_volatility(df)
        assert vol == 0.01  # default fallback

    def test_monte_carlo_scenarios(self):
        from src.fx.forecast_service import _monte_carlo_scenarios

        prophet_fc = pd.DataFrame({
            "ds": pd.date_range("2026-06-01", periods=5, freq="D"),
            "yhat": [1650.0, 1652.0, 1648.0, 1655.0, 1660.0],
            "yhat_lower": [1640.0, 1642.0, 1638.0, 1645.0, 1650.0],
            "yhat_upper": [1660.0, 1662.0, 1658.0, 1665.0, 1670.0],
        })
        scenarios = _monte_carlo_scenarios(prophet_fc, volatility=0.01, num_simulations=1000)
        assert len(scenarios) == 5
        for s in scenarios:
            assert "date" in s
            assert "base_rate" in s
            assert "best_case_rate" in s
            assert "worst_case_rate" in s
            assert s["base_rate"] > 0
            assert s["best_case_rate"] <= s["base_rate"] <= s["worst_case_rate"]

    def test_monte_carlo_handles_zero_base(self):
        from src.fx.forecast_service import _monte_carlo_scenarios

        prophet_fc = pd.DataFrame({
            "ds": [datetime(2026, 6, 1)],
            "yhat": [0.0],  # zero base should become 0.01
            "yhat_lower": [-0.1],
            "yhat_upper": [0.1],
        })
        scenarios = _monte_carlo_scenarios(prophet_fc, volatility=0.01, num_simulations=1000)
        assert len(scenarios) == 1
        assert scenarios[0]["base_rate"] > 0


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

        rates = [_make_fx_rate(rate=Decimal(str(1650 + i))) for i in range(35)]
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

        # Create 50 rate points
        rates = [
            _make_fx_rate(rate=Decimal(str(round(1650 + i * 0.5, 2))))
            for i in range(50)
        ]
        db = _mock_db_with_execute(scalars_result=rates)

        # Mock Prophet to avoid actual training
        mock_model = MagicMock()
        mock_model.history = pd.DataFrame({
            "ds": pd.date_range("2026-01-01", periods=50, freq="D"),
        })
        mock_future = pd.DataFrame({
            "ds": pd.date_range("2026-01-01", periods=60, freq="D"),
        })
        mock_model.make_future_dataframe.return_value = mock_future
        forecast_df = pd.DataFrame({
            "ds": pd.date_range("2026-01-01", periods=60, freq="D"),
            "yhat": [1650 + i * 0.5 for i in range(60)],
            "yhat_lower": [1640 + i * 0.5 for i in range(60)],
            "yhat_upper": [1660 + i * 0.5 for i in range(60)],
        })
        mock_model.predict.return_value = forecast_df

        with patch("src.fx.forecast_service._train_prophet_model", return_value=mock_model):
            forecasts = await train_and_forecast(
                db, "USDNGN", uuid.uuid4(), horizon_days=10, num_simulations=1000,
            )

        assert len(forecasts) == 10
        for fc in forecasts:
            assert fc.pair == "USDNGN"
            assert fc.model_version == "prophet-v1"
            assert fc.base_rate > 0
            assert fc.best_case_rate > 0
            assert fc.worst_case_rate > 0
        assert db.add.call_count == 10

    @pytest.mark.asyncio
    async def test_train_and_forecast_insufficient_data(self):
        from src.fx.forecast_service import train_and_forecast

        rates = [_make_fx_rate() for _ in range(5)]
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
