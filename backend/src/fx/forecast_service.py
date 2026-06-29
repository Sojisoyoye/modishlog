"""FX forecasting engine using Prophet + Monte Carlo simulation."""

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
import pandas as pd
import structlog
from prophet import Prophet
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.fx.exceptions import FXPairNotFoundError, InsufficientRateDataError
from src.fx.models import FXForecast, FXRate
from src.fx.schemas import ForecastAccuracy

logger = structlog.get_logger()

# Minimum days of history for Prophet training
MIN_TRAINING_DAYS = 30
# Forecast staleness threshold (days)
FORECAST_STALE_DAYS = 7
# Model version prefix
MODEL_VERSION = "prophet-v1"


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------


async def _fetch_historical_rates(
    db: AsyncSession,
    pair: str,
    days: int = 180,
) -> pd.DataFrame:
    """Fetch historical rates and prepare Prophet-format DataFrame."""
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
    return df


# ---------------------------------------------------------------------------
# Prophet model training
# ---------------------------------------------------------------------------


def _train_prophet_model(df: pd.DataFrame) -> Prophet:
    """Train Prophet model (CPU-intensive, should be run in thread pool)."""
    # Only fit yearly seasonality if we have at least one full year of data;
    # fitting it on <365 days causes wild extrapolation.
    has_full_year = len(df) >= 365
    model = Prophet(
        yearly_seasonality=has_full_year,
        weekly_seasonality=False,
        daily_seasonality=False,
        seasonality_mode="additive",  # additive is more stable than multiplicative with short history
        interval_width=0.80,  # 80% interval is more meaningful than 95% for planning
    )
    model.fit(df)
    return model


def _generate_prophet_forecast(
    model: Prophet,
    horizon_days: int,
) -> pd.DataFrame:
    """Generate Prophet forecast (CPU-intensive, should be run in thread pool)."""
    future = model.make_future_dataframe(periods=horizon_days)
    forecast = model.predict(future)
    # Return only future dates
    last_historical = model.history["ds"].max()
    return forecast[forecast["ds"] > last_historical][
        ["ds", "yhat", "yhat_lower", "yhat_upper"]
    ].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Monte Carlo overlay
# ---------------------------------------------------------------------------


def _monte_carlo_scenarios(
    prophet_forecast: pd.DataFrame,
    volatility: float,
    num_simulations: int = 10000,
) -> list[dict]:
    """Run Monte Carlo simulation for each forecast date using Prophet as mean."""
    scenarios = []
    rng = np.random.default_rng()

    for _, row in prophet_forecast.iterrows():
        base = row["yhat"]
        if base <= 0:
            base = 0.01

        simulated = rng.normal(
            loc=base,
            scale=volatility * base,
            size=num_simulations,
        )
        # Ensure positive rates
        simulated = simulated[simulated > 0]
        if len(simulated) < 100:
            simulated = np.array([base])

        scenarios.append(
            {
                "date": row["ds"],
                "base_rate": round(float(np.percentile(simulated, 50)), 6),
                "best_case_rate": round(float(np.percentile(simulated, 10)), 6),
                "worst_case_rate": round(float(np.percentile(simulated, 90)), 6),
                "prophet_lower": round(float(row["yhat_lower"]), 6),
                "prophet_upper": round(float(row["yhat_upper"]), 6),
            }
        )

    return scenarios


# ---------------------------------------------------------------------------
# Volatility from historical data
# ---------------------------------------------------------------------------


def _compute_volatility(df: pd.DataFrame) -> float:
    """Compute 30-day rolling volatility from historical data."""
    returns = np.diff(np.log(df["y"].values))
    if len(returns) < 2:
        return 0.01  # default low volatility
    return float(np.std(returns))


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


async def train_and_forecast(
    db: AsyncSession,
    pair: str,
    user_id: uuid.UUID,
    horizon_days: int = 180,
    num_simulations: int = 10000,
) -> list[FXForecast]:
    """Train Prophet model, generate forecasts with Monte Carlo scenarios, and store results."""
    # Fetch and prepare data
    df = await _fetch_historical_rates(db, pair, days=365)
    volatility = _compute_volatility(df)

    await logger.ainfo(
        "fx_forecast_training_started",
        pair=pair,
        data_points=len(df),
        volatility=round(volatility, 6),
    )

    # Train model and generate forecast (CPU-intensive, run in thread pool)
    model = await asyncio.to_thread(_train_prophet_model, df)
    prophet_forecast = await asyncio.to_thread(
        _generate_prophet_forecast, model, horizon_days
    )

    # Monte Carlo overlay
    scenarios = await asyncio.to_thread(
        _monte_carlo_scenarios, prophet_forecast, volatility, num_simulations
    )

    # Calculate training MAE on last 20% of data
    split_idx = int(len(df) * 0.8)
    validation = df.iloc[split_idx:]
    future_val = model.make_future_dataframe(periods=0)
    pred_val = model.predict(future_val)
    # Merge for validation dates
    pred_dates = set(pred_val["ds"].dt.date)
    val_dates = set(validation["ds"].dt.date)
    common_dates = pred_dates & val_dates
    if common_dates:
        val_df = validation[validation["ds"].dt.date.isin(common_dates)]
        pred_df = pred_val[pred_val["ds"].dt.date.isin(common_dates)]
        mae_val = float(
            np.mean(np.abs(val_df["y"].values - pred_df["yhat"].values[: len(val_df)]))
        )
    else:
        mae_val = None

    # Store forecasts
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
            mae=Decimal(str(round(mae_val, 6))) if mae_val is not None else None,
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
        training_mae=round(mae_val, 4) if mae_val else None,
    )
    return forecasts


async def get_forecast_for_date(
    db: AsyncSession,
    pair: str,
    target_date: date,
    user_id: uuid.UUID | None = None,
) -> FXForecast:
    """Get forecast for a specific date. Raises FXPairNotFoundError if no forecast exists."""
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

    # Check staleness
    age = datetime.now(timezone.utc) - forecast.generated_at
    if age > timedelta(days=FORECAST_STALE_DAYS) and user_id:
        await logger.ainfo(
            "fx_forecast_stale",
            pair=pair,
            age_days=age.days,
        )
        # Regenerate in the background; for now return stale data
        # (actual regeneration would require separate background task)

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
    # Get all forecasts that have a corresponding actual rate
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
        return ForecastAccuracy(
            pair=pair,
            total_evaluated=0,
            mean_mae=Decimal("0"),
            mean_mape=Decimal("0"),
        )

    errors: list[float] = []
    pct_errors: list[float] = []

    for fc in forecasts:
        fc_date = (
            fc.forecast_date.date()
            if isinstance(fc.forecast_date, datetime)
            else fc.forecast_date
        )
        # Find actual rate for this date
        actual_result = await db.execute(
            select(FXRate)
            .where(
                FXRate.pair == pair,
                func.date(FXRate.timestamp) == fc_date,
            )
            .order_by(FXRate.timestamp.desc())
            .limit(1)
        )
        actual = actual_result.scalar_one_or_none()
        if actual is None:
            continue

        forecast_val = float(fc.base_rate)
        actual_val = float(actual.rate)
        mae = abs(forecast_val - actual_val)
        mape = abs(forecast_val - actual_val) / actual_val * 100 if actual_val else 0

        errors.append(mae)
        pct_errors.append(mape)

        # Update individual forecast record
        fc.mae = Decimal(str(round(mae, 6)))
        fc.mape = Decimal(str(round(mape, 6)))

    if errors:
        await db.flush()

    mean_mae = Decimal(str(round(np.mean(errors), 6))) if errors else Decimal("0")
    mean_mape = (
        Decimal(str(round(np.mean(pct_errors), 6))) if pct_errors else Decimal("0")
    )

    await logger.ainfo(
        "fx_forecast_accuracy_updated",
        pair=pair,
        evaluated=len(errors),
        mean_mae=str(mean_mae),
        mean_mape=str(mean_mape),
    )

    return ForecastAccuracy(
        pair=pair,
        total_evaluated=len(errors),
        mean_mae=mean_mae,
        mean_mape=mean_mape,
    )
