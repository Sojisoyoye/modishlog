"""Cashflow domain SQLAlchemy models."""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, TimestampMixin, UUIDMixin


class PaymentFrequency(str, enum.Enum):
    """Loan repayment frequency."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class LoanStatus(str, enum.Enum):
    """Loan obligation status."""

    ACTIVE = "active"
    SETTLED = "settled"
    DEFAULTED = "defaulted"


class CashflowProjection(UUIDMixin, Base):
    """Generated cashflow forecast over a multi-month horizon."""

    __tablename__ = "cashflow_projections"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )
    projection_date: Mapped[date] = mapped_column(Date)
    horizon_months: Mapped[int] = mapped_column(Integer, default=6)
    monthly_buckets: Mapped[dict | None] = mapped_column(JSON, default=None)
    total_inflows: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    total_outflows: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    net_cashflow: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    assumptions: Mapped[dict | None] = mapped_column(JSON, default=None)
    generated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<CashflowProjection(id={self.id}, date={self.projection_date})>"


class ProjectionAssumptions(UUIDMixin, Base):
    """User-editable assumptions feeding cashflow projections."""

    __tablename__ = "projection_assumptions"

    revenue_growth_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    seasonality_factors: Mapped[dict | None] = mapped_column(JSON, default=None)
    fx_rate_assumption: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    cost_inflation_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<ProjectionAssumptions(id={self.id})>"


class DSCRRecord(UUIDMixin, Base):
    """Debt Service Coverage Ratio calculation per period."""

    __tablename__ = "dscr_records"

    period: Mapped[str] = mapped_column(String(20))
    net_operating_income: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    total_debt_service: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    dscr_value: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    is_below_threshold: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return (
            f"<DSCRRecord(id={self.id}, period={self.period}, dscr={self.dscr_value})>"
        )


class LoanObligation(UUIDMixin, TimestampMixin, Base):
    """Active loan or debt obligation."""

    __tablename__ = "loan_obligations"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )
    lender_name: Mapped[str] = mapped_column(String(255))
    principal_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    outstanding_balance: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    term_months: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    payment_frequency: Mapped[PaymentFrequency] = mapped_column(Enum(PaymentFrequency))
    monthly_payment: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(3), default="NGN")
    current_balance: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True, default=None
    )
    current_balance_currency: Mapped[str | None] = mapped_column(
        String(3), nullable=True, default=None
    )
    status: Mapped[LoanStatus] = mapped_column(
        Enum(LoanStatus), default=LoanStatus.ACTIVE
    )
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    def __repr__(self) -> str:
        return f"<LoanObligation(id={self.id}, lender={self.lender_name})>"


class CostFrequency(str, enum.Enum):
    """Operating cost payment frequency."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUALLY = "annually"


class CostCategory(str, enum.Enum):
    """Operating cost category."""

    RENT = "rent"
    UTILITIES = "utilities"
    SALARIES = "salaries"
    TRANSPORT = "transport"
    MARKETING = "marketing"
    OTHER = "other"


class OperatingCost(UUIDMixin, TimestampMixin, Base):
    """Recurring operating cost with frequency normalization."""

    __tablename__ = "operating_costs"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )
    cost_name: Mapped[str] = mapped_column(String(255))
    cost_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    frequency: Mapped[CostFrequency] = mapped_column(Enum(CostFrequency))
    monthly_equivalent: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    category: Mapped[CostCategory] = mapped_column(
        Enum(CostCategory), default=CostCategory.OTHER
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, default=None, index=True
    )

    def __repr__(self) -> str:
        return f"<OperatingCost(id={self.id}, name={self.cost_name})>"


class LoanPaymentSchedule(UUIDMixin, Base):
    """Scheduled payment within a loan amortization schedule."""

    __tablename__ = "loan_payment_schedules"

    loan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("loan_obligations.id"))
    due_date: Mapped[date] = mapped_column(Date)
    principal_portion: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    interest_portion: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    total_payment: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    paid_date: Mapped[date | None] = mapped_column(Date, default=None)

    def __repr__(self) -> str:
        return f"<LoanPaymentSchedule(id={self.id}, loan_id={self.loan_id})>"


class TriageStatus(str, enum.Enum):
    """Triage mode status."""

    ACTIVE = "active"
    RESOLVED = "resolved"


class TriageRecord(UUIDMixin, TimestampMixin, Base):
    """Liquidity squeeze triage record."""

    __tablename__ = "triage_records"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )
    trigger_date: Mapped[date] = mapped_column(Date)
    shortfall_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    horizon_days: Mapped[int] = mapped_column(Integer)
    status: Mapped[TriageStatus] = mapped_column(
        Enum(TriageStatus, values_callable=lambda x: [e.value for e in x]),
        default=TriageStatus.ACTIVE,
    )
    resolution_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, default=None
    )

    def __repr__(self) -> str:
        return f"<TriageRecord(id={self.id}, status={self.status}, shortfall={self.shortfall_amount})>"


class StressScenario(UUIDMixin, Base):
    """Stress-test scenario applied to a cashflow projection."""

    __tablename__ = "stress_scenarios"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    revenue_shock_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    fx_shock_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    cost_shock_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    base_projection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cashflow_projections.id")
    )
    stressed_buckets: Mapped[dict | None] = mapped_column(JSON, default=None)
    stressed_dscr: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    stressed_runway_months: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<StressScenario(id={self.id}, name={self.name})>"


class LiquiditySnapshot(UUIDMixin, Base):
    """Daily point-in-time snapshot of cash runway/DSCR, for 7-day trend arrows."""

    __tablename__ = "liquidity_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "business_id", "snapshot_date", name="uq_liquidity_snapshot_business_date"
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id"), nullable=False, index=True
    )
    snapshot_date: Mapped[date] = mapped_column(Date)
    cash_runway_months: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 1), default=None
    )
    cash_runway_is_finite: Mapped[bool | None] = mapped_column(Boolean, default=None)
    dscr: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), default=None)
    dscr_is_finite: Mapped[bool | None] = mapped_column(Boolean, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<LiquiditySnapshot(business_id={self.business_id}, date={self.snapshot_date})>"
