# TODO: SQLAlchemy models for the FX domain
#
# FXRate
#   - id: UUID primary key
#   - pair: String(6), indexed (e.g. "USDNGN", "EURNGN")
#   - rate: Numeric(14, 4)
#   - source: String (e.g. "cbn_official", "parallel_market", "manual", "api_provider")
#   - timestamp: DateTime with timezone (when the rate was effective)
#   - created_at: DateTime with timezone
#
# FXExposure
#   - id: UUID primary key
#   - pair: String(6)
#   - total_exposure_amount: Numeric(14, 2) - total USD-denominated exposure
#   - locked_amount: Numeric(14, 2) - portion locked at a fixed rate
#   - locked_rate: Numeric(14, 4) - the rate at which locked portion is hedged
#   - floating_amount: Numeric(14, 2) - portion exposed to market rates
#   - reference_id: UUID, nullable (order_id or liability_id)
#   - reference_type: String, nullable ("order", "loan", "payable")
#   - created_at: DateTime with timezone
#   - updated_at: DateTime with timezone
#
# FXExposureConfig
#   - id: UUID primary key
#   - locked_pct: Numeric(5, 2), default 30.00 (30%)
#   - floating_pct: Numeric(5, 2), default 70.00 (70%)
#   - updated_by: ForeignKey -> User.id
#   - updated_at: DateTime with timezone
#
# FXAlert
#   - id: UUID primary key
#   - pair: String(6)
#   - direction: String ("above" or "below")
#   - threshold_rate: Numeric(14, 4)
#   - is_enabled: Boolean, default True
#   - is_triggered: Boolean, default False
#   - triggered_at: DateTime, nullable
#   - triggered_rate: Numeric(14, 4), nullable
#   - created_by: ForeignKey -> User.id
#   - created_at: DateTime with timezone
#
# FXSimulationRun
#   - id: UUID primary key
#   - pair: String(6)
#   - horizon_days: Integer
#   - num_simulations: Integer (e.g. 10000)
#   - confidence_level: Numeric(5, 2) (e.g. 95.00)
#   - current_rate: Numeric(14, 4) - rate at time of simulation
#   - mean_projected_rate: Numeric(14, 4)
#   - p5_rate: Numeric(14, 4) - 5th percentile
#   - p50_rate: Numeric(14, 4) - median
#   - p95_rate: Numeric(14, 4) - 95th percentile
#   - var_amount: Numeric(14, 2) - Value at Risk in NGN
#   - distribution_data: JSON (histogram buckets for charting)
#   - run_by: ForeignKey -> User.id
#   - created_at: DateTime with timezone
