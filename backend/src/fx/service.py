# TODO: Async service functions for the FX domain
#
# --- FX Rate Ingestion ---
# async def ingest_rate(db, rate_in: FXRateIngest, user_id: UUID) -> FXRate
#   - Validate pair format
#   - Store new rate record
#   - Check if any FXAlerts should be triggered by this rate
#
# async def get_current_rate(db, pair: str) -> FXRate
#   - Return most recent rate for the pair
#   - Raise FXPairNotFoundError if no data exists
#
# async def get_all_current_rates(db) -> list[FXRate]
#   - Return latest rate for each tracked pair
#
# async def get_rate_history(db, pair: str, date_from: date, date_to: date) -> FXRateHistory
#   - Return historical rates with computed period stats (high, low, avg, pct_change)
#
# async def sync_external_rates(db) -> list[FXRate]
#   - Call external rate provider APIs (CBN, parallel market sources)
#   - Store fetched rates
#   - Check and trigger alerts
#   - Return list of newly stored rates
#
# --- Exposure Engine ---
# async def get_exposure_summary(db) -> list[ExposureSummary]
#   - Aggregate all FXExposure records by pair
#   - Compute locked/floating totals and percentages
#   - Calculate unrealized P&L based on current market rate vs locked rate
#
# async def get_exposure_detail(db) -> list[ExposureDetailRead]
#   - Return all individual exposure records with reference info
#
# async def lock_exposure(db, request: ExposureLockRequest, user_id: UUID) -> FXExposure
#   - Create or update exposure record to lock a portion at a given rate
#   - Validate locked amount does not exceed total exposure
#
# async def update_exposure_config(db, config: ExposureConfigUpdate, user_id: UUID) -> FXExposureConfig
#   - Validate locked_pct + floating_pct == 100
#   - Update config record
#
# async def get_exposure_config(db) -> FXExposureConfig
#
# async def recalculate_exposures(db) -> None
#   - Recompute all exposure records based on current orders and liabilities
#   - Apply exposure config split (default 30/70)
#
# --- FX Alerts ---
# async def create_alert(db, alert_in: FXAlertCreate, user_id: UUID) -> FXAlert
# async def list_alerts(db) -> list[FXAlert]
# async def update_alert(db, alert_id: UUID, alert_in: FXAlertUpdate) -> FXAlert
# async def delete_alert(db, alert_id: UUID) -> None
# async def get_triggered_alerts(db) -> list[FXAlert]
#
# async def check_alerts(db, pair: str, current_rate: Decimal) -> list[FXAlert]
#   - Check all enabled alerts for the pair
#   - Trigger alerts where rate crosses threshold in specified direction
#   - Send notifications for triggered alerts
#
# --- Monte Carlo Simulation ---
# async def run_simulation(db, request: SimulationRequest, user_id: UUID) -> FXSimulationRun
#   - Fetch historical rates for the pair (e.g. last 252 trading days)
#   - Compute daily log returns and volatility
#   - Run geometric Brownian motion Monte Carlo (num_simulations paths)
#   - Compute percentiles (p5, p50, p95), mean, VaR
#   - Build histogram distribution buckets
#   - Store results in FXSimulationRun
#
# async def get_simulation(db, sim_id: UUID) -> FXSimulationRun
#   - Raise SimulationNotFoundError if missing
#
# async def get_simulation_distribution(db, sim_id: UUID) -> SimulationDistribution
#   - Return distribution buckets for charting
