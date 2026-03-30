# TODO: Pydantic schemas for the FX domain
#
# --- FX Rate Schemas ---
# FXRateIngest
#   - pair: str (e.g. "USDNGN", validated against known pairs)
#   - rate: Decimal (> 0)
#   - source: str (validated: "cbn_official", "parallel_market", "manual", "api_provider")
#   - timestamp: datetime | None (defaults to now if omitted)
#
# FXRateRead
#   - id: UUID
#   - pair: str
#   - rate: Decimal
#   - source: str
#   - timestamp: datetime
#   - created_at: datetime
#
# FXRateHistory
#   - pair: str
#   - rates: list[FXRateRead]
#   - period_high: Decimal
#   - period_low: Decimal
#   - period_avg: Decimal
#   - pct_change: float
#
# --- Exposure Schemas ---
# ExposureSummary
#   - pair: str
#   - total_exposure: Decimal
#   - locked_amount: Decimal
#   - locked_pct: float
#   - floating_amount: Decimal
#   - floating_pct: float
#   - weighted_locked_rate: Decimal
#   - current_market_rate: Decimal
#   - unrealized_pnl: Decimal (gain/loss from floating portion vs locked rate)
#
# ExposureDetailRead
#   - id: UUID
#   - pair: str
#   - total_exposure_amount: Decimal
#   - locked_amount, locked_rate, floating_amount
#   - reference_id: UUID | None
#   - reference_type: str | None
#
# ExposureLockRequest
#   - pair: str
#   - amount_to_lock: Decimal
#   - lock_rate: Decimal
#   - reference_id: UUID | None
#   - reference_type: str | None
#
# ExposureConfigUpdate
#   - locked_pct: Decimal (0-100, must sum to 100 with floating_pct)
#   - floating_pct: Decimal (0-100)
#
# ExposureConfigRead
#   - locked_pct: Decimal
#   - floating_pct: Decimal
#   - updated_by: UUID
#   - updated_at: datetime
#
# --- Alert Schemas ---
# FXAlertCreate
#   - pair: str
#   - direction: str ("above" | "below")
#   - threshold_rate: Decimal
#
# FXAlertRead
#   - id: UUID
#   - pair, direction, threshold_rate
#   - is_enabled: bool
#   - is_triggered: bool
#   - triggered_at: datetime | None
#   - triggered_rate: Decimal | None
#   - created_by: UUID
#   - created_at: datetime
#
# FXAlertUpdate
#   - threshold_rate: Decimal | None
#   - is_enabled: bool | None
#
# --- Monte Carlo Simulation Schemas ---
# SimulationRequest
#   - pair: str
#   - horizon_days: int (1-365)
#   - num_simulations: int (1000-100000, default 10000)
#   - confidence_level: Decimal (e.g. 95.0)
#
# SimulationResult
#   - id: UUID
#   - pair: str
#   - horizon_days, num_simulations, confidence_level
#   - current_rate: Decimal
#   - mean_projected_rate: Decimal
#   - p5_rate, p50_rate, p95_rate: Decimal
#   - var_amount: Decimal
#   - created_at: datetime
#
# SimulationDistribution
#   - sim_id: UUID
#   - buckets: list[dict] (rate_range_start, rate_range_end, frequency, cumulative_probability)
