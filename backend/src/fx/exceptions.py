# TODO: Domain-specific exceptions for the FX domain
#
# FXPairNotFoundError(Exception)
#   - Raised when no rate data exists for a requested currency pair.
#   - Attributes: pair
#
# InvalidFXPairError(Exception)
#   - Raised when an FX pair string is malformed or not in the supported list.
#   - Attributes: pair, supported_pairs
#
# FXAlertNotFoundError(Exception)
#   - Raised when an alert lookup by ID yields no result.
#   - Attributes: alert_id
#
# ExposureConfigError(Exception)
#   - Raised when exposure config is invalid (e.g. locked_pct + floating_pct != 100).
#   - Attributes: locked_pct, floating_pct, reason
#
# ExposureLockExceededError(Exception)
#   - Raised when attempting to lock more exposure than the total outstanding amount.
#   - Attributes: pair, requested_lock, total_exposure, already_locked
#
# SimulationNotFoundError(Exception)
#   - Raised when a simulation run lookup by ID yields no result.
#   - Attributes: sim_id
#
# InsufficientRateDataError(Exception)
#   - Raised when there is not enough historical rate data to run a Monte Carlo simulation.
#   - Attributes: pair, available_days, required_days
#
# ExternalRateSyncError(Exception)
#   - Raised when the external FX rate provider API call fails.
#   - Attributes: provider, status_code, error_message
