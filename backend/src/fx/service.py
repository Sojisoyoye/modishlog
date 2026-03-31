"""FX domain business logic."""

import math
import random
import statistics
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.fx.exceptions import (
    ExposureConfigError,
    ExposureLockExceededError,
    ExternalRateSyncError,
    FXAlertNotFoundError,
    FXPairNotFoundError,
    InsufficientRateDataError,
    SimulationNotFoundError,
)
from src.fx.models import (
    AlertDirection,
    FXAlert,
    FXExposure,
    FXExposureConfig,
    FXRate,
    FXSimulationRun,
    RateSource,
)
from src.fx.schemas import (
    ExposureConfigUpdate,
    ExposureLockRequest,
    FXAlertCreate,
    FXAlertUpdate,
    FXRateHistory,
    FXRateIngest,
    FXRateRead,
    SimulationRequest,
    VolatilityRead,
)

logger = structlog.get_logger()

# Minimum historical data points required for simulation
MIN_SIMULATION_DAYS = 30


# ---------------------------------------------------------------------------
# FX Rate Ingestion
# ---------------------------------------------------------------------------


async def ingest_rate(
    db: AsyncSession,
    data: FXRateIngest,
    user_id: uuid.UUID,
) -> FXRate:
    """Ingest a single FX rate observation and check alerts."""
    ts = data.timestamp or datetime.now(timezone.utc)

    rate = FXRate(
        pair=data.pair,
        rate=data.rate,
        source=RateSource(data.source),
        timestamp=ts,
        created_at=datetime.now(timezone.utc),
    )
    db.add(rate)
    await db.flush()

    # Check alerts asynchronously
    await check_alerts(db, data.pair, data.rate)

    await logger.ainfo(
        "fx_rate_ingested",
        pair=data.pair,
        rate=str(data.rate),
        source=data.source,
    )
    return rate


async def get_current_rate(
    db: AsyncSession,
    pair: str,
) -> FXRate:
    """Get the most recent rate for a currency pair."""
    result = await db.execute(
        select(FXRate)
        .where(FXRate.pair == pair)
        .order_by(FXRate.timestamp.desc())
        .limit(1)
    )
    rate = result.scalar_one_or_none()
    if not rate:
        raise FXPairNotFoundError(pair)
    return rate


async def get_all_current_rates(db: AsyncSession) -> list[FXRate]:
    """Get the latest rate for each tracked pair."""
    # Get distinct pairs
    pairs_result = await db.execute(
        select(FXRate.pair).distinct()
    )
    pairs = [row[0] for row in pairs_result.all()]

    rates = []
    for pair in pairs:
        rate = await get_current_rate(db, pair)
        rates.append(rate)
    return rates


async def get_rate_history(
    db: AsyncSession,
    pair: str,
    date_from: date,
    date_to: date,
) -> FXRateHistory:
    """Get historical rates with computed statistics."""
    result = await db.execute(
        select(FXRate)
        .where(
            FXRate.pair == pair,
            FXRate.timestamp >= datetime.combine(date_from, datetime.min.time()),
            FXRate.timestamp <= datetime.combine(date_to, datetime.max.time()),
        )
        .order_by(FXRate.timestamp.asc())
    )
    rates = list(result.scalars().all())

    if not rates:
        raise FXPairNotFoundError(pair)

    rate_values = [r.rate for r in rates]
    period_high = max(rate_values)
    period_low = min(rate_values)
    period_avg = sum(rate_values, Decimal("0")) / len(rate_values)

    first_rate = rate_values[0]
    last_rate = rate_values[-1]
    pct_change = float((last_rate - first_rate) / first_rate * 100) if first_rate else 0.0

    rate_reads = [FXRateRead.model_validate(r) for r in rates]

    return FXRateHistory(
        pair=pair,
        rates=rate_reads,
        period_high=period_high,
        period_low=period_low,
        period_avg=period_avg,
        pct_change=round(pct_change, 4),
    )


async def get_rate_for_date(
    db: AsyncSession,
    pair: str,
    rate_date: date,
) -> FXRate:
    """Get rate for a specific date, falling back to nearest previous date."""
    # Try exact date
    result = await db.execute(
        select(FXRate)
        .where(
            FXRate.pair == pair,
            func.date(FXRate.timestamp) == rate_date,
        )
        .order_by(FXRate.timestamp.desc())
        .limit(1)
    )
    rate = result.scalar_one_or_none()
    if rate:
        return rate

    # Fallback to nearest previous date
    result = await db.execute(
        select(FXRate)
        .where(
            FXRate.pair == pair,
            func.date(FXRate.timestamp) <= rate_date,
        )
        .order_by(FXRate.timestamp.desc())
        .limit(1)
    )
    rate = result.scalar_one_or_none()
    if rate:
        await logger.ainfo(
            "fx_rate_fallback",
            pair=pair,
            requested_date=str(rate_date),
            actual_date=str(rate.timestamp),
        )
        return rate

    raise FXPairNotFoundError(pair)


async def sync_external_rates(db: AsyncSession) -> list[FXRate]:
    """Sync rates from external FX API provider."""
    if not settings.FX_API_KEY:
        raise ExternalRateSyncError("fx_api", None, "FX_API_KEY not configured")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                settings.FX_API_URL,
                headers={"Authorization": f"Bearer {settings.FX_API_KEY}"},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as e:
        raise ExternalRateSyncError(
            "fx_api", e.response.status_code, str(e)
        )
    except httpx.RequestError as e:
        raise ExternalRateSyncError("fx_api", None, str(e))

    stored_rates: list[FXRate] = []
    now = datetime.now(timezone.utc)

    # Expected response format: {"rates": {"USDNGN": 1650.25, ...}}
    rates_data = data.get("rates", {})
    for pair, rate_value in rates_data.items():
        fx_rate = FXRate(
            pair=pair,
            rate=Decimal(str(rate_value)),
            source=RateSource.API_PROVIDER,
            timestamp=now,
            created_at=now,
        )
        db.add(fx_rate)
        stored_rates.append(fx_rate)

    await db.flush()

    # Check alerts for each new rate
    for r in stored_rates:
        await check_alerts(db, r.pair, r.rate)

    await logger.ainfo(
        "fx_rates_synced",
        count=len(stored_rates),
        pairs=[r.pair for r in stored_rates],
    )
    return stored_rates


async def backfill_historical_data(
    db: AsyncSession,
    pair: str,
    date_from: date,
    date_to: date,
) -> int:
    """Backfill historical rate data from external API. Returns count of records inserted."""
    if not settings.FX_API_KEY:
        raise ExternalRateSyncError("fx_api", None, "FX_API_KEY not configured")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.FX_API_URL}/history",
                params={
                    "pair": pair,
                    "start_date": date_from.isoformat(),
                    "end_date": date_to.isoformat(),
                },
                headers={"Authorization": f"Bearer {settings.FX_API_KEY}"},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as e:
        raise ExternalRateSyncError(
            "fx_api", e.response.status_code, str(e)
        )
    except httpx.RequestError as e:
        raise ExternalRateSyncError("fx_api", None, str(e))

    # Expected format: {"history": [{"date": "2025-01-01", "rate": 1650.25}, ...]}
    history = data.get("history", [])
    count = 0
    for entry in history:
        ts = datetime.fromisoformat(entry["date"]).replace(tzinfo=timezone.utc)
        # Check for duplicates
        existing = await db.execute(
            select(FXRate).where(
                FXRate.pair == pair,
                func.date(FXRate.timestamp) == ts.date(),
                FXRate.source == RateSource.API_PROVIDER,
            )
        )
        if existing.scalar_one_or_none():
            continue

        fx_rate = FXRate(
            pair=pair,
            rate=Decimal(str(entry["rate"])),
            source=RateSource.API_PROVIDER,
            timestamp=ts,
            created_at=datetime.now(timezone.utc),
        )
        db.add(fx_rate)
        count += 1

    await db.flush()
    await logger.ainfo(
        "fx_backfill_complete",
        pair=pair,
        records_inserted=count,
    )
    return count


# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------


async def calculate_volatility(
    db: AsyncSession,
    pair: str,
    days: int = 30,
) -> VolatilityRead:
    """Calculate rolling standard deviation of daily rate changes."""
    result = await db.execute(
        select(FXRate)
        .where(FXRate.pair == pair)
        .order_by(FXRate.timestamp.desc())
        .limit(days + 1)  # Need one extra for change calc
    )
    rates = list(result.scalars().all())
    rates.reverse()  # Oldest first

    if len(rates) < 2:
        raise FXPairNotFoundError(pair)

    # Calculate daily log returns
    daily_returns: list[float] = []
    for i in range(1, len(rates)):
        prev = float(rates[i - 1].rate)
        curr = float(rates[i].rate)
        if prev > 0:
            daily_returns.append(math.log(curr / prev))

    if len(daily_returns) < 2:
        raise InsufficientRateDataError(pair, len(daily_returns), 2)

    vol = Decimal(str(round(statistics.stdev(daily_returns), 8)))

    return VolatilityRead(
        pair=pair,
        days=days,
        volatility=vol,
        data_points=len(daily_returns),
    )


# ---------------------------------------------------------------------------
# Exposure Engine
# ---------------------------------------------------------------------------


async def get_exposure_summary(
    db: AsyncSession,
) -> list[dict]:
    """Aggregate all exposure records by pair with P&L calculation."""
    result = await db.execute(
        select(
            FXExposure.pair,
            func.sum(FXExposure.total_exposure_amount).label("total_exposure"),
            func.sum(FXExposure.locked_amount).label("locked"),
            func.sum(FXExposure.floating_amount).label("floating"),
        ).group_by(FXExposure.pair)
    )
    rows = result.all()

    summaries = []
    for row in rows:
        pair = row[0]
        total_exp = row[1] or Decimal("0")
        locked = row[2] or Decimal("0")
        floating = row[3] or Decimal("0")

        # Get weighted locked rate
        rate_result = await db.execute(
            select(
                func.sum(FXExposure.locked_amount * FXExposure.locked_rate),
                func.sum(FXExposure.locked_amount),
            ).where(FXExposure.pair == pair, FXExposure.locked_amount > 0)
        )
        rate_row = rate_result.one()
        weighted_locked_rate = (
            rate_row[0] / rate_row[1]
            if rate_row[1] and rate_row[1] > 0
            else Decimal("0")
        )

        # Get current market rate
        try:
            current = await get_current_rate(db, pair)
            market_rate = current.rate
        except FXPairNotFoundError:
            market_rate = Decimal("0")

        # Unrealized P&L on floating portion
        unrealized = floating * (market_rate - weighted_locked_rate) if weighted_locked_rate else Decimal("0")

        locked_pct = float(locked / total_exp * 100) if total_exp else 0.0
        floating_pct = float(floating / total_exp * 100) if total_exp else 0.0

        summaries.append({
            "pair": pair,
            "total_exposure": total_exp,
            "locked_amount": locked,
            "locked_pct": round(locked_pct, 2),
            "floating_amount": floating,
            "floating_pct": round(floating_pct, 2),
            "weighted_locked_rate": weighted_locked_rate,
            "current_market_rate": market_rate,
            "unrealized_pnl": unrealized,
        })
    return summaries


async def get_exposure_detail(
    db: AsyncSession,
) -> list[FXExposure]:
    """Return all individual exposure records."""
    result = await db.execute(
        select(FXExposure).order_by(FXExposure.pair)
    )
    return list(result.scalars().all())


async def lock_exposure(
    db: AsyncSession,
    data: ExposureLockRequest,
    user_id: uuid.UUID,
) -> FXExposure:
    """Create an exposure record to lock a portion at a given rate."""
    # Check total existing exposure for the pair
    result = await db.execute(
        select(
            func.coalesce(func.sum(FXExposure.total_exposure_amount), 0),
            func.coalesce(func.sum(FXExposure.locked_amount), 0),
        ).where(FXExposure.pair == data.pair)
    )
    row = result.one()
    total_exposure = row[0]
    already_locked = row[1]

    available = total_exposure - already_locked
    if data.amount_to_lock > available and total_exposure > 0:
        raise ExposureLockExceededError(
            data.pair, data.amount_to_lock, total_exposure, already_locked
        )

    exposure = FXExposure(
        pair=data.pair,
        total_exposure_amount=data.amount_to_lock,
        locked_amount=data.amount_to_lock,
        locked_rate=data.lock_rate,
        floating_amount=Decimal("0"),
        reference_id=data.reference_id,
        reference_type=data.reference_type,
    )
    db.add(exposure)
    await db.flush()

    await logger.ainfo(
        "fx_exposure_locked",
        pair=data.pair,
        amount=str(data.amount_to_lock),
        rate=str(data.lock_rate),
    )
    return exposure


async def get_exposure_config(db: AsyncSession) -> FXExposureConfig | None:
    """Get the current exposure split configuration."""
    result = await db.execute(
        select(FXExposureConfig).order_by(FXExposureConfig.updated_at.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def update_exposure_config(
    db: AsyncSession,
    data: ExposureConfigUpdate,
    user_id: uuid.UUID,
) -> FXExposureConfig:
    """Update exposure config. locked_pct + floating_pct must equal 100."""
    if data.locked_pct + data.floating_pct != Decimal("100"):
        raise ExposureConfigError(
            data.locked_pct,
            data.floating_pct,
            "locked_pct + floating_pct must equal 100",
        )

    config = FXExposureConfig(
        locked_pct=data.locked_pct,
        floating_pct=data.floating_pct,
        updated_by=user_id,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(config)
    await db.flush()

    await logger.ainfo(
        "fx_exposure_config_updated",
        locked_pct=str(data.locked_pct),
        floating_pct=str(data.floating_pct),
    )
    return config


# ---------------------------------------------------------------------------
# FX Alerts
# ---------------------------------------------------------------------------


async def create_alert(
    db: AsyncSession,
    data: FXAlertCreate,
    user_id: uuid.UUID,
) -> FXAlert:
    """Create a new rate threshold alert."""
    alert = FXAlert(
        pair=data.pair,
        direction=AlertDirection(data.direction),
        threshold_rate=data.threshold_rate,
        is_enabled=True,
        is_triggered=False,
        created_by=user_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(alert)
    await db.flush()

    await logger.ainfo(
        "fx_alert_created",
        pair=data.pair,
        direction=data.direction,
        threshold=str(data.threshold_rate),
    )
    return alert


async def list_alerts(db: AsyncSession) -> list[FXAlert]:
    """List all FX alerts."""
    result = await db.execute(
        select(FXAlert).order_by(FXAlert.created_at.desc())
    )
    return list(result.scalars().all())


async def get_alert(db: AsyncSession, alert_id: uuid.UUID) -> FXAlert:
    """Get a specific alert by ID."""
    result = await db.execute(
        select(FXAlert).where(FXAlert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise FXAlertNotFoundError(alert_id)
    return alert


async def update_alert(
    db: AsyncSession,
    alert_id: uuid.UUID,
    data: FXAlertUpdate,
) -> FXAlert:
    """Update an alert's threshold or enabled status."""
    alert = await get_alert(db, alert_id)

    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(alert, field, value)

    await db.flush()
    await logger.ainfo("fx_alert_updated", alert_id=str(alert_id))
    return alert


async def delete_alert(db: AsyncSession, alert_id: uuid.UUID) -> None:
    """Delete an alert."""
    alert = await get_alert(db, alert_id)
    await db.delete(alert)
    await db.flush()
    await logger.ainfo("fx_alert_deleted", alert_id=str(alert_id))


async def get_triggered_alerts(db: AsyncSession) -> list[FXAlert]:
    """List recently triggered alerts."""
    result = await db.execute(
        select(FXAlert)
        .where(FXAlert.is_triggered.is_(True))
        .order_by(FXAlert.triggered_at.desc())
    )
    return list(result.scalars().all())


async def check_alerts(
    db: AsyncSession,
    pair: str,
    current_rate: Decimal,
) -> list[FXAlert]:
    """Check all enabled alerts for a pair and trigger those that cross the threshold."""
    result = await db.execute(
        select(FXAlert).where(
            FXAlert.pair == pair,
            FXAlert.is_enabled.is_(True),
            FXAlert.is_triggered.is_(False),
        )
    )
    alerts = list(result.scalars().all())
    triggered: list[FXAlert] = []

    for alert in alerts:
        should_trigger = False
        if alert.direction == AlertDirection.ABOVE and current_rate >= alert.threshold_rate:
            should_trigger = True
        elif alert.direction == AlertDirection.BELOW and current_rate <= alert.threshold_rate:
            should_trigger = True

        if should_trigger:
            alert.is_triggered = True
            alert.triggered_at = datetime.now(timezone.utc)
            alert.triggered_rate = current_rate
            triggered.append(alert)
            await logger.ainfo(
                "fx_alert_triggered",
                alert_id=str(alert.id),
                pair=pair,
                direction=alert.direction.value,
                threshold=str(alert.threshold_rate),
                current_rate=str(current_rate),
            )

    if triggered:
        await db.flush()

    return triggered


# ---------------------------------------------------------------------------
# Monte Carlo Simulation
# ---------------------------------------------------------------------------


async def run_simulation(
    db: AsyncSession,
    data: SimulationRequest,
    user_id: uuid.UUID,
) -> FXSimulationRun:
    """Run a Monte Carlo simulation for FX rate projection."""
    # Fetch historical rates
    result = await db.execute(
        select(FXRate)
        .where(FXRate.pair == data.pair)
        .order_by(FXRate.timestamp.desc())
        .limit(252)  # ~1 year of trading days
    )
    rates = list(result.scalars().all())
    rates.reverse()  # Oldest first

    if len(rates) < MIN_SIMULATION_DAYS:
        raise InsufficientRateDataError(
            data.pair, len(rates), MIN_SIMULATION_DAYS
        )

    # Compute daily log returns
    rate_values = [float(r.rate) for r in rates]
    daily_returns: list[float] = []
    for i in range(1, len(rate_values)):
        if rate_values[i - 1] > 0:
            daily_returns.append(math.log(rate_values[i] / rate_values[i - 1]))

    mu = statistics.mean(daily_returns)
    sigma = statistics.stdev(daily_returns)
    current_rate_val = rate_values[-1]

    # Run simulations using geometric Brownian motion
    final_rates: list[float] = []
    for _ in range(data.num_simulations):
        price = current_rate_val
        for _ in range(data.horizon_days):
            drift = (mu - 0.5 * sigma**2)
            shock = sigma * random.gauss(0, 1)
            price *= math.exp(drift + shock)
        final_rates.append(price)

    final_rates.sort()
    n = len(final_rates)

    mean_rate = statistics.mean(final_rates)
    p5 = final_rates[int(n * 0.05)]
    p50 = final_rates[int(n * 0.50)]
    p95 = final_rates[int(n * 0.95)]

    # VaR at confidence level
    conf = float(data.confidence_level) / 100.0
    var_idx = int(n * (1 - conf))
    var_rate = final_rates[var_idx]
    var_amount = abs(current_rate_val - var_rate)

    # Build distribution buckets (20 buckets)
    bucket_count = 20
    min_rate = final_rates[0]
    max_rate = final_rates[-1]
    bucket_width = (max_rate - min_rate) / bucket_count if max_rate != min_rate else 1
    buckets = []
    for i in range(bucket_count):
        start = min_rate + i * bucket_width
        end = start + bucket_width
        freq = sum(1 for r in final_rates if start <= r < end)
        cum_prob = sum(1 for r in final_rates if r < end) / n
        buckets.append({
            "rate_range_start": round(start, 4),
            "rate_range_end": round(end, 4),
            "frequency": freq,
            "cumulative_probability": round(cum_prob, 4),
        })

    sim = FXSimulationRun(
        pair=data.pair,
        horizon_days=data.horizon_days,
        num_simulations=data.num_simulations,
        confidence_level=data.confidence_level,
        current_rate=Decimal(str(round(current_rate_val, 6))),
        mean_projected_rate=Decimal(str(round(mean_rate, 6))),
        p5_rate=Decimal(str(round(p5, 6))),
        p50_rate=Decimal(str(round(p50, 6))),
        p95_rate=Decimal(str(round(p95, 6))),
        var_amount=Decimal(str(round(var_amount, 6))),
        distribution_data=buckets,
        run_by=user_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(sim)
    await db.flush()

    await logger.ainfo(
        "fx_simulation_complete",
        pair=data.pair,
        horizon=data.horizon_days,
        simulations=data.num_simulations,
        mean_rate=str(round(mean_rate, 4)),
    )
    return sim


async def get_simulation(
    db: AsyncSession,
    sim_id: uuid.UUID,
) -> FXSimulationRun:
    """Retrieve a simulation run by ID."""
    result = await db.execute(
        select(FXSimulationRun).where(FXSimulationRun.id == sim_id)
    )
    sim = result.scalar_one_or_none()
    if not sim:
        raise SimulationNotFoundError(sim_id)
    return sim


async def get_simulation_distribution(
    db: AsyncSession,
    sim_id: uuid.UUID,
) -> dict:
    """Get distribution buckets for a simulation run."""
    sim = await get_simulation(db, sim_id)
    return {
        "sim_id": sim.id,
        "buckets": sim.distribution_data or [],
    }
