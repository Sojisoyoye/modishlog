"""FX API routes."""

import csv
import io
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.core.csv_utils import csv_safe
from src.core.database import get_db
from src.fx.exceptions import (
    ExposureConfigError,
    ExposureLockExceededError,
    ExternalRateSyncError,
    FXAlertNotFoundError,
    FXPairNotFoundError,
    InsufficientRateDataError,
    SimulationNotFoundError,
)
from src.fx.models import FXRate
from src.fx.schemas import (
    ExposureConfigRead,
    ExposureConfigUpdate,
    ExposureDetailRead,
    ExposureLockRequest,
    ExposureSummary,
    ForecastAccuracy,
    ForecastRangeResponse,
    ForecastRead,
    ForecastRequest,
    FXAlertCreate,
    FXAlertRead,
    FXAlertUpdate,
    FXRateHistory,
    FXRateIngest,
    FXRateRead,
    LiveRateRead,
    SimulationDistribution,
    SimulationRequest,
    SimulationResult,
    VolatilityRead,
)
from src.fx.service import (
    get_live_usdngn_rate,
    backfill_historical_data,
    calculate_volatility,
    create_alert,
    delete_alert,
    get_all_current_rates,
    get_current_rate,
    get_exposure_config,
    get_exposure_detail,
    get_exposure_summary,
    get_rate_for_date,
    get_rate_history,
    get_simulation,
    get_simulation_distribution,
    get_triggered_alerts,
    ingest_rate,
    list_alerts,
    lock_exposure,
    run_simulation,
    sync_external_rates,
    update_alert,
    update_exposure_config,
)

router = APIRouter(dependencies=[Depends(get_current_active_user)])


# ---------------------------------------------------------------------------
# FX Rate Ingestion
# ---------------------------------------------------------------------------


@router.post(
    "/rates/ingest", response_model=FXRateRead, status_code=status.HTTP_201_CREATED
)
async def ingest_rate_endpoint(
    body: FXRateIngest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Manually ingest an FX rate observation."""
    return await ingest_rate(db, body, current_user.id)


@router.get("/rates/current", response_model=list[FXRateRead])
async def current_rates_endpoint(db: AsyncSession = Depends(get_db)):
    """Get current rates for all tracked pairs."""
    return await get_all_current_rates(db)


@router.get("/export.csv")
async def export_fx_csv_endpoint(
    pair: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export FX rate observations as a CSV file."""
    query = select(FXRate)
    if pair is not None:
        query = query.where(FXRate.pair == pair)
    if date_from is not None:
        query = query.where(
            FXRate.timestamp >= datetime.combine(date_from, datetime.min.time())
        )
    if date_to is not None:
        query = query.where(
            FXRate.timestamp <= datetime.combine(date_to, datetime.max.time())
        )
    query = query.order_by(FXRate.timestamp.desc())

    result = await db.execute(query)
    rates = list(result.scalars().all())

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "pair", "rate", "source", "timestamp"])
    for rate in rates:
        writer.writerow(
            [
                str(rate.id),
                csv_safe(rate.pair),
                str(rate.rate),
                csv_safe(rate.source.value if rate.source else ""),
                rate.timestamp.isoformat() if rate.timestamp else "",
            ]
        )
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=fx_rates_export.csv"},
    )


@router.get("/live", response_model=LiveRateRead)
async def live_rate_endpoint(db: AsyncSession = Depends(get_db)):
    """Get live USD/NGN rate, served from 4-hour cache or fetched from free API."""
    try:
        rate, fetched_at, cached = await get_live_usdngn_rate(db)
        return LiveRateRead(usd_ngn=rate, fetched_at=fetched_at, cached=cached)
    except ExternalRateSyncError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.get("/rates/{pair}", response_model=FXRateRead)
async def get_rate_endpoint(
    pair: str,
    db: AsyncSession = Depends(get_db),
):
    """Get current rate for a specific pair."""
    try:
        return await get_current_rate(db, pair)
    except FXPairNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/rates/{pair}/history", response_model=FXRateHistory)
async def rate_history_endpoint(
    pair: str,
    date_from: date,
    date_to: date,
    db: AsyncSession = Depends(get_db),
):
    """Get historical rate data for a pair."""
    try:
        return await get_rate_history(db, pair, date_from, date_to)
    except FXPairNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/rates/{pair}/date", response_model=FXRateRead)
async def rate_for_date_endpoint(
    pair: str,
    rate_date: date,
    db: AsyncSession = Depends(get_db),
):
    """Get rate for a specific date with nearest-previous fallback."""
    try:
        return await get_rate_for_date(db, pair, rate_date)
    except FXPairNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/rates/sync", response_model=list[FXRateRead])
async def sync_rates_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Trigger sync from external rate providers."""
    try:
        return await sync_external_rates(db)
    except ExternalRateSyncError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.post("/rates/backfill")
async def backfill_endpoint(
    pair: str,
    date_from: date,
    date_to: date,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Backfill historical data from API."""
    try:
        count = await backfill_historical_data(db, pair, date_from, date_to)
        return {"pair": pair, "records_inserted": count}
    except ExternalRateSyncError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.get("/volatility/{pair}", response_model=VolatilityRead)
async def volatility_endpoint(
    pair: str,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Get volatility metric for a pair."""
    try:
        return await calculate_volatility(db, pair, days)
    except (FXPairNotFoundError, InsufficientRateDataError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------------------------------------------------------------------------
# Exposure Engine
# ---------------------------------------------------------------------------


@router.get("/exposure", response_model=list[ExposureSummary])
async def exposure_summary_endpoint(db: AsyncSession = Depends(get_db)):
    """Get current FX exposure summary."""
    data = await get_exposure_summary(db)
    return [ExposureSummary(**d) for d in data]


@router.get("/exposure/detail", response_model=list[ExposureDetailRead])
async def exposure_detail_endpoint(db: AsyncSession = Depends(get_db)):
    """Get detailed exposure records."""
    return await get_exposure_detail(db)


@router.post(
    "/exposure/lock",
    response_model=ExposureDetailRead,
    status_code=status.HTTP_201_CREATED,
)
async def lock_exposure_endpoint(
    body: ExposureLockRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Lock a portion of exposure at a specific rate."""
    try:
        return await lock_exposure(db, body, current_user.id)
    except ExposureLockExceededError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/exposure/config", response_model=ExposureConfigRead | None)
async def get_exposure_config_endpoint(db: AsyncSession = Depends(get_db)):
    """Get current exposure split configuration."""
    return await get_exposure_config(db)


@router.put("/exposure/config", response_model=ExposureConfigRead)
async def update_exposure_config_endpoint(
    body: ExposureConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update exposure split config (locked_pct + floating_pct must = 100)."""
    try:
        return await update_exposure_config(db, body, current_user.id)
    except ExposureConfigError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ---------------------------------------------------------------------------
# FX Alerts
# ---------------------------------------------------------------------------


@router.post("/alerts", response_model=FXAlertRead, status_code=status.HTTP_201_CREATED)
async def create_alert_endpoint(
    body: FXAlertCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a rate threshold alert."""
    return await create_alert(db, body, current_user.id)


@router.get("/alerts", response_model=list[FXAlertRead])
async def list_alerts_endpoint(db: AsyncSession = Depends(get_db)):
    """List all FX alerts."""
    return await list_alerts(db)


@router.put("/alerts/{alert_id}", response_model=FXAlertRead)
async def update_alert_endpoint(
    alert_id: uuid.UUID,
    body: FXAlertUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update an alert."""
    try:
        return await update_alert(db, alert_id, body)
    except FXAlertNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_endpoint(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Delete an alert."""
    try:
        await delete_alert(db, alert_id)
    except FXAlertNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/alerts/triggered", response_model=list[FXAlertRead])
async def triggered_alerts_endpoint(db: AsyncSession = Depends(get_db)):
    """List recently triggered alerts."""
    return await get_triggered_alerts(db)


# ---------------------------------------------------------------------------
# Monte Carlo Simulation
# ---------------------------------------------------------------------------


@router.post(
    "/simulate", response_model=SimulationResult, status_code=status.HTTP_201_CREATED
)
async def run_simulation_endpoint(
    body: SimulationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Run a Monte Carlo simulation."""
    try:
        return await run_simulation(db, body, current_user.id)
    except InsufficientRateDataError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/simulate/{sim_id}", response_model=SimulationResult)
async def get_simulation_endpoint(
    sim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get results of a previous simulation."""
    try:
        return await get_simulation(db, sim_id)
    except SimulationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/simulate/{sim_id}/distribution", response_model=SimulationDistribution)
async def simulation_distribution_endpoint(
    sim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get probability distribution for charting."""
    try:
        data = await get_simulation_distribution(db, sim_id)
        return SimulationDistribution(**data)
    except SimulationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------------------------------------------------------------------------
# FX Forecasting (Prophet + Monte Carlo)
# ---------------------------------------------------------------------------


@router.post(
    "/forecast/generate",
    response_model=list[ForecastRead],
    status_code=status.HTTP_201_CREATED,
)
async def generate_forecast_endpoint(
    body: ForecastRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Train Prophet model and generate FX forecast with Monte Carlo scenarios."""
    from src.fx.forecast_service import train_and_forecast

    try:
        return await train_and_forecast(
            db,
            body.pair,
            current_user.id,
            body.horizon_days,
            body.num_simulations,
        )
    except (FXPairNotFoundError, InsufficientRateDataError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/forecast/{pair}/{target_date}", response_model=ForecastRead)
async def get_forecast_for_date_endpoint(
    pair: str,
    target_date: date,
    db: AsyncSession = Depends(get_db),
):
    """Get forecast for a specific date."""
    from src.fx.forecast_service import get_forecast_for_date

    try:
        return await get_forecast_for_date(db, pair, target_date)
    except FXPairNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/forecast/{pair}", response_model=ForecastRangeResponse)
async def get_forecast_range_endpoint(
    pair: str,
    date_from: date,
    date_to: date,
    db: AsyncSession = Depends(get_db),
):
    """Get forecast time series for a date range."""
    from src.fx.forecast_service import get_forecast_range

    forecasts = await get_forecast_range(db, pair, date_from, date_to)
    model_ver = forecasts[0].model_version if forecasts else ""
    forecast_reads = [ForecastRead.model_validate(f) for f in forecasts]
    return ForecastRangeResponse(
        pair=pair,
        forecasts=forecast_reads,
        model_version=model_ver,
    )


@router.get("/forecast/{pair}/accuracy", response_model=ForecastAccuracy)
async def forecast_accuracy_endpoint(
    pair: str,
    db: AsyncSession = Depends(get_db),
):
    """Get forecast accuracy metrics."""
    from src.fx.forecast_service import update_forecast_accuracy

    return await update_forecast_accuracy(db, pair)
