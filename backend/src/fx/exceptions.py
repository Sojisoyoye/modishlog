"""FX domain exceptions."""

import uuid
from decimal import Decimal


class FXPairNotFoundError(Exception):
    """Raised when no rate data exists for a requested currency pair."""

    def __init__(self, pair: str) -> None:
        self.pair = pair
        super().__init__(f"No rate data found for pair '{pair}'")


class InvalidFXPairError(Exception):
    """Raised when an FX pair string is malformed or not in the supported list."""

    def __init__(self, pair: str, supported_pairs: list[str]) -> None:
        self.pair = pair
        self.supported_pairs = supported_pairs
        super().__init__(
            f"Invalid FX pair '{pair}'. Supported: {', '.join(supported_pairs)}"
        )


class FXRateNotFoundError(Exception):
    """Raised when an FX rate lookup by ID yields no result."""

    def __init__(self, rate_id: uuid.UUID) -> None:
        self.rate_id = rate_id
        super().__init__(f"FX rate {rate_id} not found")


class FXAlertNotFoundError(Exception):
    """Raised when an alert lookup by ID yields no result."""

    def __init__(self, alert_id: uuid.UUID) -> None:
        self.alert_id = alert_id
        super().__init__(f"FX alert {alert_id} not found")


class ExposureConfigError(Exception):
    """Raised when exposure config is invalid (e.g. locked_pct + floating_pct != 100)."""

    def __init__(self, locked_pct: Decimal, floating_pct: Decimal, reason: str) -> None:
        self.locked_pct = locked_pct
        self.floating_pct = floating_pct
        self.reason = reason
        super().__init__(f"Exposure config error: {reason}")


class ExposureLockExceededError(Exception):
    """Raised when attempting to lock more exposure than the total outstanding amount."""

    def __init__(
        self,
        pair: str,
        requested_lock: Decimal,
        total_exposure: Decimal,
        already_locked: Decimal,
    ) -> None:
        self.pair = pair
        self.requested_lock = requested_lock
        self.total_exposure = total_exposure
        self.already_locked = already_locked
        super().__init__(
            f"Cannot lock {requested_lock} for {pair}: "
            f"total exposure {total_exposure}, already locked {already_locked}"
        )


class SimulationNotFoundError(Exception):
    """Raised when a simulation run lookup by ID yields no result."""

    def __init__(self, sim_id: uuid.UUID) -> None:
        self.sim_id = sim_id
        super().__init__(f"Simulation run {sim_id} not found")


class InsufficientRateDataError(Exception):
    """Raised when there is not enough historical rate data to run a Monte Carlo simulation."""

    def __init__(self, pair: str, available_days: int, required_days: int) -> None:
        self.pair = pair
        self.available_days = available_days
        self.required_days = required_days
        super().__init__(
            f"Insufficient rate data for {pair}: "
            f"have {available_days} days, need {required_days}"
        )


class ExternalRateSyncError(Exception):
    """Raised when the external FX rate provider API call fails."""

    def __init__(
        self, provider: str, status_code: int | None, error_message: str
    ) -> None:
        self.provider = provider
        self.status_code = status_code
        self.error_message = error_message
        super().__init__(
            f"External rate sync failed ({provider}): "
            f"status={status_code}, {error_message}"
        )


class ForecastTimeoutError(Exception):
    """Raised when a CPU-bound ML forecast exceeds its asyncio.to_thread timeout."""

    def __init__(self, operation: str, timeout_seconds: float) -> None:
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"{operation} timed out after {timeout_seconds}s. "
            "The server is under load — try again shortly."
        )
