"""FX forecasting engine using Geometric Brownian Motion + Monte Carlo."""

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.fx.exceptions import FXPairNotFoundError, InsufficientRateDataError
from src.fx.models import FXForecast, FXRate
from src.fx.schemas import ForecastAccuracy

logger = structlog.get_logger()

MIN_TRAINING_DAYS = 30
MODEL_VERSION = "gbm-v1"

# Max annualised drift allowed in either direction (~20% pa).
# Prevents short-term noise being extrapolated into implausible trends.
MAX_ANNUAL_DRIFT = 0.20
MAX_DAILY_DRIFT = np.log(1 + MAX_ANNUAL_DRIFT) / 365


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------


async def _fetch_historical_rates(
    db: AsyncSession,
    pair: str,
    days: int = 365,
) -> pd.DataFrame:
    """Fetch historical rates and return a deduplicated daily DataFrame."""
    result = await db.execute(
        select(FXRate)
        .where(FXRate.pair == pair)
        .order_by(FXRate.timestamp.asc())
        .limit(days)
    )
    rates = list(result.scalars().all())

    if len(rates) < MIN_TRAINING_DAYS:
        raise InsufficientRateDataError(pair, len(rates), MIN_TRAINING_DAYS)

    df = pd.DataFrame(
        [{"ds": r.timestamp.replace(tzinfo=None), "y": float(r.rate)} for r in rates]
    )
    # Keep one rate per calendar day (last timestamp wins) to avoid duplicate-date
    # issues that inflate uncertainty estimates in any model.
    df["date"] = df["ds"].dt.date
    df = df.sort_values("ds").drop_duplicates(subset="date", keep="last")
    df = df.drop(columns="date").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Geometric Brownian Motion Monte Carlo
# ---------------------------------------------------------------------------


def _gbm_forecast(
    df: pd.DataFrame,
    horizon_days: int,
    num_simulations: int = 2000,
) -> list[dict]:
    """
    Geometric Brownian Motion Monte Carlo forecast for FX rates.

    Why GBM instead of Prophet:
    - Prophet extrapolates trend linearly; with short history that produces
      implausible values (₦300 or ₦2800 after 6 months).
    - GBM is the standard finance model for exchange rates.  Each simulated
      path is a connected random walk, so uncertainty fans out correctly as
      vol * sqrt(t).  The rate can never go negative.
    - With ~90 days of history the drift estimate is unreliable, so it is
      capped at ±20% pa.  The uncertainty band is driven by daily volatility,
      which is well-estimated even from 30 days of data.
    """
    prices = df["y"].values
    log_returns = np.diff(np.log(prices))

    # Estimate parameters from the most recent 60 days; older data may reflect
    # different macro conditions.
    recent = log_returns[-60:] if len(log_returns) > 60 else log_returns
    raw_drift = float(np.mean(recent))
    daily_drift = float(np.clip(raw_drift, -MAX_DAILY_DRIFT, MAX_DAILY_DRIFT))
    daily_vol = float(np.std(recent))

    # Safety floor on volatility (at least 0.1 % per day)
    daily_vol = max(daily_vol, 0.001)

    S0 = float(prices[-1])
    last_date = df["ds"].iloc[-1]
    rng = np.random.default_rng()

    # Simulate all paths in one vectorised operation.
    # Shape: (num_simulations, horizon_days)
    Z = rng.standard_normal((num_simulations, horizon_days))
    log_increments = (daily_drift - 0.5 * daily_vol**2) + daily_vol * Z
    # cumsum gives log-path, exp gives price path
    paths = S0 * np.exp(np.cumsum(log_increments, axis=1))

    scenarios: list[dict] = []
    for t in range(horizon_days):
        day_prices = paths[:, t]
        target_date = last_date + pd.Timedelta(days=t + 1)
        scenarios.append(
            {
                "date": target_date,
                "base_rate": round(float(np.percentile(day_prices, 50)), 6),
                "best_case_rate": round(float(np.percentile(day_prices, 10)), 6),
                "worst_case_rate": round(float(np.percentile(day_prices, 90)), 6),
                "prophet_lower": round(float(np.percentile(day_prices, 10)), 6),
                "prophet_upper": round(float(np.percentile(day_prices, 90)), 6),
            }
        )

    return scenarios


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


async def train_and_forecast(
    db: AsyncSession,
    pair: str,
    user_id: uuid.UUID,
    horizon_days: int = 180,
    num_simulations: int = 2000,
) -> list[FXForecast]:
    """Generate GBM Monte Carlo forecasts and store results."""
    df = await _fetch_historical_rates(db, pair, days=365)

    await logger.ainfo("fx_forecast_training_started", pair=pair, data_points=len(df))

    # Compute first; only delete stale rows after a successful run so a GBM
    # failure never leaves the pair with zero forecasts.
    scenarios = await asyncio.to_thread(
        _gbm_forecast, df, horizon_days, num_simulations
    )

    await db.execute(delete(FXForecast).where(FXForecast.pair == pair))

    now = datetime.now(timezone.utc)
    forecasts: list[FXForecast] = []
    for scenario in scenarios:
        forecast = FXForecast(
            pair=pair,
            forecast_date=scenario["date"].replace(tzinfo=timezone.utc),
            base_rate=Decimal(str(scenario["base_rate"])),
            best_case_rate=Decimal(str(scenario["best_case_rate"])),
            worst_case_rate=Decimal(str(scenario["worst_case_rate"])),
            prophet_lower=Decimal(str(scenario["prophet_lower"])),
            prophet_upper=Decimal(str(scenario["prophet_upper"])),
            model_version=MODEL_VERSION,
            mae=None,
            mape=None,
            generated_at=now,
            generated_by=user_id,
        )
        db.add(forecast)
        forecasts.append(forecast)

    await db.flush()
    await logger.ainfo(
        "fx_forecast_complete",
        pair=pair,
        horizon_days=horizon_days,
        scenarios_generated=len(forecasts),
    )
    return forecasts


async def get_forecast_for_date(
    db: AsyncSession,
    pair: str,
    target_date: date,
    user_id: uuid.UUID | None = None,
) -> FXForecast:
    """Get forecast for a specific date."""
    result = await db.execute(
        select(FXForecast)
        .where(
            FXForecast.pair == pair,
            func.date(FXForecast.forecast_date) == target_date,
        )
        .order_by(FXForecast.generated_at.desc())
        .limit(1)
    )
    forecast = result.scalar_one_or_none()
    if forecast is None:
        raise FXPairNotFoundError(pair)
    return forecast


async def get_forecast_range(
    db: AsyncSession,
    pair: str,
    date_from: date,
    date_to: date,
) -> list[FXForecast]:
    """Get forecast time series for a date range."""
    result = await db.execute(
        select(FXForecast)
        .where(
            FXForecast.pair == pair,
            func.date(FXForecast.forecast_date) >= date_from,
            func.date(FXForecast.forecast_date) <= date_to,
        )
        .order_by(FXForecast.forecast_date.asc())
    )
    return list(result.scalars().all())


async def update_forecast_accuracy(
    db: AsyncSession,
    pair: str,
) -> ForecastAccuracy:
    """Compare past forecasts to actual rates and compute MAE/MAPE."""
    forecasts_result = await db.execute(
        select(FXForecast)
        .where(
            FXForecast.pair == pair,
            FXForecast.forecast_date <= datetime.now(timezone.utc),
        )
        .order_by(FXForecast.forecast_date.asc())
    )
    forecasts = list(forecasts_result.scalars().all())

    if not forecasts:
        return ForecastAccuracy(pair=pair, total_evaluated=0, mean_mae=Decimal("0"), mean_mape=Decimal("0"))

    errors: list[float] = []
    pct_errors: list[float] = []

    for fc in forecasts:
        fc_date = fc.forecast_date.date() if isinstance(fc.forecast_date, datetime) else fc.forecast_date
        actual_result = await db.execute(
            select(FXRate)
            .where(FXRate.pair == pair, func.date(FXRate.timestamp) == fc_date)
            .order_by(FXRate.timestamp.desc())
            .limit(1)
        )
        actual = actual_result.scalar_one_or_none()
        if actual is None:
            continue
        forecast_val = float(fc.base_rate)
        actual_val = float(actual.rate)
        errors.append(abs(forecast_val - actual_val))
        pct_errors.append(abs(forecast_val - actual_val) / actual_val * 100 if actual_val else 0)
        fc.mae = Decimal(str(round(errors[-1], 6)))
        fc.mape = Decimal(str(round(pct_errors[-1], 6)))

    if errors:
        await db.flush()

    return ForecastAccuracy(
        pair=pair,
        total_evaluated=len(errors),
        mean_mae=Decimal(str(round(float(np.mean(errors)), 6))) if errors else Decimal("0"),
        mean_mape=Decimal(str(round(float(np.mean(pct_errors)), 6))) if pct_errors else Decimal("0"),
    )
