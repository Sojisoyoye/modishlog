"""FX domain SQLAlchemy models."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin


class RateSource(str, enum.Enum):
    """Source of the FX rate quote."""

    CBN_OFFICIAL = "cbn_official"
    PARALLEL_MARKET = "parallel_market"
    MANUAL = "manual"
    API_PROVIDER = "api_provider"


class AlertDirection(str, enum.Enum):
    """Direction for FX rate alerts."""

    ABOVE = "above"
    BELOW = "below"


class FXRate(UUIDMixin, Base):
    """Point-in-time FX rate observation."""

    __tablename__ = "fx_rates"

    pair: Mapped[str] = mapped_column(String(6), index=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    source: Mapped[RateSource] = mapped_column(Enum(RateSource))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<FXRate(pair={self.pair}, rate={self.rate})>"


class FXExposure(UUIDMixin, TimestampMixin, Base):
    """Currency exposure position tracking."""

    __tablename__ = "fx_exposures"

    pair: Mapped[str] = mapped_column(String(6))
    total_exposure_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    locked_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    locked_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    floating_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    reference_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    reference_type: Mapped[str | None] = mapped_column(String(50), default=None)

    def __repr__(self) -> str:
        return f"<FXExposure(id={self.id}, pair={self.pair})>"


class FXExposureConfig(UUIDMixin, Base):
    """Configuration for hedge split percentages."""

    __tablename__ = "fx_exposure_configs"

    locked_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("30.00"))
    floating_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("70.00"))
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<FXExposureConfig(id={self.id})>"


class FXAlert(UUIDMixin, Base):
    """User-defined FX rate threshold alert."""

    __tablename__ = "fx_alerts"

    pair: Mapped[str] = mapped_column(String(6))
    direction: Mapped[AlertDirection] = mapped_column(Enum(AlertDirection))
    threshold_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    triggered_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), default=None)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<FXAlert(id={self.id}, pair={self.pair}, direction={self.direction})>"


class FXForecast(UUIDMixin, Base):
    """Stored FX rate forecast from Prophet + Monte Carlo."""

    __tablename__ = "fx_forecasts"

    pair: Mapped[str] = mapped_column(String(6), index=True)
    forecast_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    base_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    best_case_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    worst_case_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    prophet_lower: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    prophet_upper: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    model_version: Mapped[str] = mapped_column(String(50))
    mae: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), default=None)
    mape: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), default=None)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    def __repr__(self) -> str:
        return f"<FXForecast(pair={self.pair}, date={self.forecast_date})>"


class FXSimulationRun(UUIDMixin, Base):
    """Results from a Monte Carlo FX simulation."""

    __tablename__ = "fx_simulation_runs"

    pair: Mapped[str] = mapped_column(String(6))
    horizon_days: Mapped[int] = mapped_column(Integer)
    num_simulations: Mapped[int] = mapped_column(Integer)
    confidence_level: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    current_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    mean_projected_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    p5_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    p50_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    p95_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    var_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    distribution_data: Mapped[dict | None] = mapped_column(JSON, default=None)
    run_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<FXSimulationRun(id={self.id}, pair={self.pair})>"
