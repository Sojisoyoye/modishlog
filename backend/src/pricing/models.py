"""Pricing domain SQLAlchemy models."""

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

from src.core.database import Base, TimestampMixin, UUIDMixin


class RecommendationStatus(str, enum.Enum):
    """Status of a pricing recommendation."""

    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    EXPIRED = "expired"


class DemandElasticity(UUIDMixin, Base):
    """Price elasticity of demand calculated per product."""

    __tablename__ = "demand_elasticities"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"), unique=True
    )
    elasticity_coefficient: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    r_squared: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    data_points_used: Mapped[int] = mapped_column(Integer)
    calculation_date: Mapped[date] = mapped_column(Date)
    price_range_min: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    price_range_max: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    demand_curve_data: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<DemandElasticity(id={self.id}, product_id={self.product_id})>"


class MarginTarget(UUIDMixin, TimestampMixin, Base):
    """Target margin configuration per product or category."""

    __tablename__ = "margin_targets"

    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id"), default=None
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_categories.id"), default=None
    )
    target_margin_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    min_margin_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    priority: Mapped[int] = mapped_column(Integer, default=1)
    set_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    def __repr__(self) -> str:
        return f"<MarginTarget(id={self.id}, target={self.target_margin_pct}%)>"


class PricingRecommendation(UUIDMixin, Base):
    """AI-generated pricing recommendation for a product."""

    __tablename__ = "pricing_recommendations"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    current_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    recommended_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    expected_demand_change_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    expected_revenue_change_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    expected_margin_change_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    reasoning: Mapped[str] = mapped_column(Text)
    status: Mapped[RecommendationStatus] = mapped_column(
        Enum(RecommendationStatus), default=RecommendationStatus.PENDING
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    applied_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<PricingRecommendation(id={self.id}, product_id={self.product_id})>"


class ProductMixTarget(UUIDMixin, TimestampMixin, Base):
    """Target revenue-mix percentage per product category."""

    __tablename__ = "product_mix_targets"

    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product_categories.id"), unique=True
    )
    target_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))

    def __repr__(self) -> str:
        return f"<ProductMixTarget(id={self.id}, category_id={self.category_id}, target={self.target_pct}%)>"


class CrossSubsidyAnalysis(UUIDMixin, Base):
    """Portfolio-level cross-subsidy analysis snapshot."""

    __tablename__ = "cross_subsidy_analyses"

    analysis_date: Mapped[date] = mapped_column(Date)
    portfolio_total_margin: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    subsidy_matrix: Mapped[dict | None] = mapped_column(JSON, default=None)
    high_margin_products: Mapped[dict | None] = mapped_column(JSON, default=None)
    low_margin_products: Mapped[dict | None] = mapped_column(JSON, default=None)
    recommendations: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<CrossSubsidyAnalysis(id={self.id}, date={self.analysis_date})>"


class PricingScenario(UUIDMixin, Base):
    """Saved price-FX sensitivity scenario for the playground."""

    __tablename__ = "pricing_scenarios"

    name: Mapped[str] = mapped_column(String(255))
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id"), default=None
    )
    selling_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    quantity: Mapped[int] = mapped_column(Integer)
    results: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<PricingScenario(id={self.id}, name={self.name})>"
