"""AI Engine domain SQLAlchemy models."""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, UUIDMixin


class RecommendationCategory(str, enum.Enum):
    """Domain category for AI recommendations."""

    PRICING = "pricing"
    INVENTORY = "inventory"
    FX = "fx"
    CASHFLOW = "cashflow"
    ORDERS = "orders"


class RecommendationPriority(str, enum.Enum):
    """Priority level for recommendations."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ActionType(str, enum.Enum):
    """Type of action an AI recommendation suggests."""

    PRICE_CHANGE = "price_change"
    REORDER = "reorder"
    FX_LOCK = "fx_lock"
    COST_CUT = "cost_cut"
    USD_PURCHASE = "usd_purchase"


class RecommendationStatus(str, enum.Enum):
    """Lifecycle status of an AI recommendation."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    EXPIRED = "expired"
    APPLIED = "applied"


class RiskTolerance(str, enum.Enum):
    """Risk appetite setting for USD strategy."""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class PurchaseScheduleStatus(str, enum.Enum):
    """Status of a USD purchase schedule entry."""

    UPCOMING = "upcoming"
    EXECUTED = "executed"
    SKIPPED = "skipped"
    EXPIRED = "expired"


class ReorderStatus(str, enum.Enum):
    """Status for reorder suggestions."""

    PENDING = "pending"
    APPROVED = "approved"
    DISMISSED = "dismissed"
    CONVERTED_TO_ORDER = "converted_to_order"


class AIRecommendation(UUIDMixin, Base):
    """Cross-domain AI-generated recommendation."""

    __tablename__ = "ai_recommendations"

    category: Mapped[RecommendationCategory] = mapped_column(
        Enum(RecommendationCategory)
    )
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[RecommendationPriority] = mapped_column(
        Enum(RecommendationPriority)
    )
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    expected_impact: Mapped[dict | None] = mapped_column(JSON, default=None)
    action_type: Mapped[ActionType] = mapped_column(Enum(ActionType))
    action_payload: Mapped[dict | None] = mapped_column(JSON, default=None)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    reference_type: Mapped[str | None] = mapped_column(String(50), default=None)
    status: Mapped[RecommendationStatus] = mapped_column(
        Enum(RecommendationStatus), default=RecommendationStatus.PENDING
    )
    dismissed_reason: Mapped[str | None] = mapped_column(Text, default=None)
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), default=None
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    measured_outcome: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<AIRecommendation(id={self.id}, category={self.category})>"


class USDStrategyConfig(UUIDMixin, Base):
    """Configuration for automated USD buying strategy."""

    __tablename__ = "usd_strategy_configs"

    target_usd_balance: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    current_usd_balance: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    risk_tolerance: Mapped[RiskTolerance] = mapped_column(Enum(RiskTolerance))
    max_single_purchase_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    preferred_rate_percentile: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    lookback_days: Mapped[int] = mapped_column(Integer)
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<USDStrategyConfig(id={self.id})>"


class USDPurchaseSchedule(UUIDMixin, Base):
    """Scheduled or executed USD purchase recommendation."""

    __tablename__ = "usd_purchase_schedules"

    strategy_config_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usd_strategy_configs.id")
    )
    recommended_date: Mapped[date] = mapped_column(Date)
    recommended_amount_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    recommended_rate_ceiling: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    reasoning: Mapped[str] = mapped_column(Text)
    status: Mapped[PurchaseScheduleStatus] = mapped_column(
        Enum(PurchaseScheduleStatus), default=PurchaseScheduleStatus.UPCOMING
    )
    executed_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), default=None)
    executed_amount_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), default=None
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<USDPurchaseSchedule(id={self.id})>"


class ReorderSuggestion(UUIDMixin, Base):
    """AI-generated suggestion to reorder a product."""

    __tablename__ = "reorder_suggestions"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    current_stock: Mapped[int] = mapped_column(Integer)
    reorder_point: Mapped[int] = mapped_column(Integer)
    suggested_order_quantity: Mapped[int] = mapped_column(Integer)
    economic_order_quantity: Mapped[int] = mapped_column(Integer)
    safety_stock: Mapped[int] = mapped_column(Integer)
    lead_time_days: Mapped[int] = mapped_column(Integer)
    avg_daily_demand: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    demand_variability: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    estimated_stockout_date: Mapped[date | None] = mapped_column(Date, default=None)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    reasoning: Mapped[str] = mapped_column(Text)
    status: Mapped[ReorderStatus] = mapped_column(
        Enum(ReorderStatus), default=ReorderStatus.PENDING
    )
    converted_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("purchase_orders.id"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<ReorderSuggestion(id={self.id}, product_id={self.product_id})>"


class ReorderConfig(UUIDMixin, Base):
    """Global configuration for reorder point calculations."""

    __tablename__ = "reorder_configs"

    default_lead_time_days: Mapped[int] = mapped_column(Integer, default=30)
    safety_stock_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), default=Decimal("1.50")
    )
    service_level_target: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("95.00")
    )
    demand_lookback_days: Mapped[int] = mapped_column(Integer, default=90)
    holding_cost_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<ReorderConfig(id={self.id})>"
