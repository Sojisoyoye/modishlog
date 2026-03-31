"""Pricing domain service: demand forecasting, margin optimization, recommendations."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import structlog
from prophet import Prophet
from scipy.optimize import minimize
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.pricing.exceptions import (
    ElasticityNotFoundError,
    InsufficientPriceDataError,
    OptimizationInfeasibleError,
    RecommendationExpiredError,
    RecommendationNotFoundError,
)
from src.pricing.models import (
    CrossSubsidyAnalysis,
    DemandElasticity,
    MarginTarget,
    PricingRecommendation,
    RecommendationStatus,
)
from src.products.models import PriceHistory, Product
from src.sales.models import Sale, SaleStatus

logger = structlog.get_logger()

MIN_DATA_POINTS = 10
RECOMMENDATION_MAX_AGE_DAYS = 30
DEFAULT_ELASTICITY = Decimal("-1.0000")
DEFAULT_TARGET_MARGIN = Decimal("35.00")


# ---------------------------------------------------------------------------
# Demand Forecasting
# ---------------------------------------------------------------------------


async def _fetch_sales_history(
    db: AsyncSession,
    product_id: uuid.UUID,
    days: int = 180,
) -> pd.DataFrame:
    """Fetch daily aggregated sales for Prophet format."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(Sale.sale_date, func.sum(Sale.quantity))
        .where(
            Sale.product_id == product_id,
            Sale.status == SaleStatus.COMPLETED,
            Sale.sale_date >= cutoff.date(),
        )
        .group_by(Sale.sale_date)
        .order_by(Sale.sale_date.asc())
    )
    rows = result.all()

    if len(rows) < MIN_DATA_POINTS:
        raise InsufficientPriceDataError(product_id, len(rows), MIN_DATA_POINTS)

    df = pd.DataFrame(
        [{"ds": row[0], "y": float(row[1])} for row in rows]
    )
    df["ds"] = pd.to_datetime(df["ds"])
    return df


def _train_demand_model(df: pd.DataFrame) -> Prophet:
    """Train Prophet demand model (CPU-intensive)."""
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        seasonality_mode="multiplicative",
        interval_width=0.90,
    )
    model.fit(df)
    return model


def _generate_demand_forecast(
    model: Prophet, horizon_days: int
) -> pd.DataFrame:
    """Generate Prophet demand forecast (CPU-intensive)."""
    future = model.make_future_dataframe(periods=horizon_days)
    forecast = model.predict(future)
    last_historical = model.history["ds"].max()
    return forecast[forecast["ds"] > last_historical][
        ["ds", "yhat", "yhat_lower", "yhat_upper"]
    ].reset_index(drop=True)


async def calculate_demand_forecast(
    db: AsyncSession,
    product_id: uuid.UUID,
    horizon_days: int = 90,
    proposed_price: Decimal | None = None,
) -> dict:
    """Generate demand forecast with optional price elasticity adjustment."""
    df = await _fetch_sales_history(db, product_id)

    model = await asyncio.to_thread(_train_demand_model, df)
    forecast_df = await asyncio.to_thread(
        _generate_demand_forecast, model, horizon_days
    )

    # Apply price elasticity adjustment if proposed_price given
    multiplier = 1.0
    if proposed_price is not None:
        product = await _get_product(db, product_id)
        elasticity = await _get_elasticity_coefficient(db, product_id)
        price_change_pct = float(
            (proposed_price - product.selling_price) / product.selling_price
        )
        multiplier = 1 + float(elasticity) * price_change_pct

    forecasts = []
    total_demand = 0.0
    for _, row in forecast_df.iterrows():
        yhat = max(0, row["yhat"] * multiplier)
        lower = max(0, row["yhat_lower"] * multiplier)
        upper = max(0, row["yhat_upper"] * multiplier)
        total_demand += yhat
        forecasts.append({
            "date": row["ds"].date(),
            "demand": round(yhat, 2),
            "demand_lower": round(lower, 2),
            "demand_upper": round(upper, 2),
        })

    return {
        "product_id": product_id,
        "horizon_days": horizon_days,
        "forecasts": forecasts,
        "total_projected_demand": round(total_demand, 2),
    }


# ---------------------------------------------------------------------------
# Price Elasticity
# ---------------------------------------------------------------------------


async def _get_product(db: AsyncSession, product_id: uuid.UUID) -> Product:
    """Fetch product or raise."""
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if product is None:
        from src.products.exceptions import ProductNotFoundError
        raise ProductNotFoundError(product_id)
    return product


async def _get_elasticity_coefficient(
    db: AsyncSession, product_id: uuid.UUID
) -> Decimal:
    """Get elasticity coefficient for a product, or default."""
    result = await db.execute(
        select(DemandElasticity).where(
            DemandElasticity.product_id == product_id
        )
    )
    elasticity = result.scalar_one_or_none()
    if elasticity is None:
        return DEFAULT_ELASTICITY
    return elasticity.elasticity_coefficient


async def calculate_price_elasticity_impact(
    db: AsyncSession,
    product_id: uuid.UUID,
    proposed_price: Decimal,
) -> dict:
    """Calculate demand impact for a proposed price change."""
    product = await _get_product(db, product_id)
    elasticity = await _get_elasticity_coefficient(db, product_id)

    current_price = product.selling_price
    price_change_pct = float((proposed_price - current_price) / current_price)
    demand_impact_pct = float(elasticity) * price_change_pct

    return {
        "product_id": product_id,
        "current_price": current_price,
        "proposed_price": proposed_price,
        "price_change_pct": round(price_change_pct, 4),
        "elasticity_coefficient": elasticity,
        "demand_impact_pct": round(demand_impact_pct, 4),
        "projected_demand_multiplier": round(1 + demand_impact_pct, 4),
    }


async def get_elasticity(
    db: AsyncSession, product_id: uuid.UUID
) -> DemandElasticity:
    """Get elasticity record for a product."""
    result = await db.execute(
        select(DemandElasticity).where(
            DemandElasticity.product_id == product_id
        )
    )
    elasticity = result.scalar_one_or_none()
    if elasticity is None:
        raise ElasticityNotFoundError(product_id)
    return elasticity


async def update_elasticity_config(
    db: AsyncSession,
    product_id: uuid.UUID,
    coefficient: Decimal,
) -> DemandElasticity:
    """Create or update elasticity coefficient for a product."""
    result = await db.execute(
        select(DemandElasticity).where(
            DemandElasticity.product_id == product_id
        )
    )
    elasticity = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if elasticity is None:
        elasticity = DemandElasticity(
            product_id=product_id,
            elasticity_coefficient=coefficient,
            r_squared=Decimal("0"),
            data_points_used=0,
            calculation_date=now.date(),
            price_range_min=Decimal("0"),
            price_range_max=Decimal("0"),
            created_at=now,
        )
        db.add(elasticity)
    else:
        elasticity.elasticity_coefficient = coefficient
        elasticity.calculation_date = now.date()

    await db.flush()
    return elasticity


# ---------------------------------------------------------------------------
# Portfolio Margin
# ---------------------------------------------------------------------------


async def calculate_portfolio_margin(
    db: AsyncSession,
    target_margin: Decimal = DEFAULT_TARGET_MARGIN,
) -> dict:
    """Calculate blended portfolio margin from last 30 days of sales."""
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).date()

    # Get all active products with recent sales
    result = await db.execute(
        select(
            Product.id,
            Product.name,
            Product.unit_cost,
            Product.selling_price,
            func.sum(Sale.quantity).label("qty"),
            func.sum(Sale.total_amount).label("revenue"),
        )
        .join(Sale, Sale.product_id == Product.id)
        .where(
            Product.is_active.is_(True),
            Sale.status == SaleStatus.COMPLETED,
            Sale.sale_date >= thirty_days_ago,
        )
        .group_by(Product.id, Product.name, Product.unit_cost, Product.selling_price)
    )
    rows = result.all()

    products = []
    total_revenue = Decimal("0")
    total_cogs = Decimal("0")

    for row in rows:
        pid, name, unit_cost, selling_price, qty, revenue = row
        cogs = unit_cost * qty
        margin_pct = float((revenue - cogs) / revenue * 100) if revenue else 0.0

        products.append({
            "product_id": pid,
            "product_name": name,
            "unit_cost": unit_cost,
            "selling_price": selling_price,
            "margin_pct": round(margin_pct, 2),
            "revenue_30d": revenue,
            "cogs_30d": cogs,
            "quantity_30d": qty,
        })
        total_revenue += revenue
        total_cogs += cogs

    blended_margin = (
        (total_revenue - total_cogs) / total_revenue * 100
        if total_revenue
        else Decimal("0")
    )

    return {
        "blended_margin": Decimal(str(round(float(blended_margin), 2))),
        "target_margin": target_margin,
        "margin_gap": Decimal(str(round(float(blended_margin) - float(target_margin), 2))),
        "total_revenue": total_revenue,
        "total_cogs": total_cogs,
        "products": products,
    }


# ---------------------------------------------------------------------------
# Margin Targets
# ---------------------------------------------------------------------------


async def set_margin_target(
    db: AsyncSession,
    data,
    user_id: uuid.UUID,
) -> MarginTarget:
    """Create a margin target."""
    target = MarginTarget(
        product_id=data.product_id,
        category_id=data.category_id,
        target_margin_pct=data.target_margin_pct,
        min_margin_pct=data.min_margin_pct,
        priority=data.priority,
        set_by=user_id,
    )
    db.add(target)
    await db.flush()
    return target


async def get_margin_targets(db: AsyncSession) -> list[MarginTarget]:
    """List all margin targets."""
    result = await db.execute(
        select(MarginTarget).order_by(MarginTarget.priority.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# SciPy Price Optimization
# ---------------------------------------------------------------------------


def _optimize_prices(
    products: list[dict],
    target_margin: float = 0.35,
) -> list[dict]:
    """Use SciPy to find optimal prices maximizing profit subject to margin target.

    products: list of dicts with keys:
        product_id, unit_cost, selling_price, avg_daily_sales, elasticity
    """
    if not products:
        return []

    x0 = [float(p["selling_price"]) for p in products]

    def _calc_totals(prices):
        total_rev = 0.0
        total_cogs = 0.0
        for i, p in enumerate(products):
            new_price = prices[i]
            old_price = float(p["selling_price"])
            if old_price <= 0:
                continue
            price_change = (new_price - old_price) / old_price
            elasticity = float(p.get("elasticity", -1.0))
            demand_mult = max(0.1, 1 + elasticity * price_change)
            projected_qty = float(p["avg_daily_sales"]) * 30 * demand_mult
            total_rev += projected_qty * new_price
            total_cogs += projected_qty * float(p["unit_cost"])
        return total_rev, total_cogs

    def objective(prices):
        total_rev, total_cogs = _calc_totals(prices)
        if total_rev <= 0:
            return 1e10
        # Maximize profit (minimize negative profit)
        return -(total_rev - total_cogs)

    def margin_constraint(prices):
        total_rev, total_cogs = _calc_totals(prices)
        if total_rev <= 0:
            return -1.0
        margin = (total_rev - total_cogs) / total_rev
        return margin - target_margin  # >= 0 means margin meets target

    # Bounds: min 10% margin above cost, max 3x cost
    bounds = [
        (float(p["unit_cost"]) * 1.10, float(p["unit_cost"]) * 3.0)
        for p in products
    ]

    constraints = [{"type": "ineq", "fun": margin_constraint}]

    result = minimize(
        objective, x0, bounds=bounds, method="SLSQP",
        constraints=constraints,
    )
    if not result.success:
        raise OptimizationInfeasibleError(result.message)

    optimized = []
    for i, p in enumerate(products):
        optimized.append({
            "product_id": p["product_id"],
            "current_price": p["selling_price"],
            "optimized_price": Decimal(str(round(result.x[i], 2))),
            "unit_cost": p["unit_cost"],
        })
    return optimized


# ---------------------------------------------------------------------------
# Pricing Recommendations
# ---------------------------------------------------------------------------


async def generate_recommendations(
    db: AsyncSession,
    target_margin: Decimal = DEFAULT_TARGET_MARGIN,
) -> list[PricingRecommendation]:
    """Generate pricing recommendations for products below target margin."""
    portfolio = await calculate_portfolio_margin(db, target_margin)

    # Get products below target margin
    below_target = [
        p for p in portfolio["products"]
        if p["margin_pct"] < float(target_margin)
    ]

    if not below_target:
        await logger.ainfo("pricing_no_recommendations_needed", margin=str(portfolio["blended_margin"]))
        return []

    # Prepare data for optimizer
    opt_inputs = []
    for p in below_target:
        elasticity = await _get_elasticity_coefficient(db, p["product_id"])
        avg_daily = p["quantity_30d"] / 30 if p["quantity_30d"] else 1
        opt_inputs.append({
            "product_id": p["product_id"],
            "product_name": p["product_name"],
            "unit_cost": p["unit_cost"],
            "selling_price": p["selling_price"],
            "avg_daily_sales": avg_daily,
            "elasticity": float(elasticity),
            "current_margin_pct": p["margin_pct"],
        })

    # Run optimization in thread pool
    try:
        optimized = await asyncio.to_thread(
            _optimize_prices, opt_inputs, float(target_margin) / 100,
        )
    except OptimizationInfeasibleError:
        return []

    # Create recommendations
    now = datetime.now(timezone.utc)
    recommendations: list[PricingRecommendation] = []

    for opt in optimized:
        current = Decimal(str(opt["current_price"]))
        recommended = opt["optimized_price"]

        if current == recommended:
            continue

        price_change_pct = float((recommended - current) / current * 100)
        elasticity = await _get_elasticity_coefficient(db, opt["product_id"])
        demand_change = float(elasticity) * price_change_pct / 100

        # Estimate margin improvement
        new_margin = float(
            (recommended - opt["unit_cost"]) / recommended * 100
        )
        margin_change = new_margin - float(
            (current - opt["unit_cost"]) / current * 100
        )

        # Determine priority
        margin_gap = float(target_margin) - float(
            (current - opt["unit_cost"]) / current * 100
        )
        if margin_gap > 5:
            priority = "HIGH"
        elif margin_gap > 2:
            priority = "MEDIUM"
        else:
            priority = "LOW"

        reasoning = (
            f"{priority} priority: Current margin gap of {margin_gap:.1f}%. "
            f"Price increase of {price_change_pct:.1f}% projected to improve "
            f"margin by {margin_change:.1f}pp with {demand_change * 100:.1f}% "
            f"demand impact (elasticity: {float(elasticity):.2f})."
        )

        rec = PricingRecommendation(
            product_id=opt["product_id"],
            current_price=current,
            recommended_price=recommended,
            expected_demand_change_pct=Decimal(str(round(demand_change * 100, 2))),
            expected_revenue_change_pct=Decimal(str(round(price_change_pct, 2))),
            expected_margin_change_pct=Decimal(str(round(margin_change, 2))),
            confidence=Decimal("75.00"),
            reasoning=reasoning,
            status=RecommendationStatus.PENDING,
            created_at=now,
        )
        db.add(rec)
        recommendations.append(rec)

    await db.flush()

    await logger.ainfo(
        "pricing_recommendations_generated",
        count=len(recommendations),
        target_margin=str(target_margin),
    )
    return recommendations


async def get_recommendations(
    db: AsyncSession,
) -> list[PricingRecommendation]:
    """Get all pending recommendations."""
    result = await db.execute(
        select(PricingRecommendation)
        .where(PricingRecommendation.status == RecommendationStatus.PENDING)
        .order_by(PricingRecommendation.created_at.desc())
    )
    return list(result.scalars().all())


async def apply_recommendation(
    db: AsyncSession,
    recommendation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> PricingRecommendation:
    """Apply a pricing recommendation: update product price."""
    result = await db.execute(
        select(PricingRecommendation).where(
            PricingRecommendation.id == recommendation_id
        )
    )
    rec = result.scalar_one_or_none()
    if rec is None:
        raise RecommendationNotFoundError(recommendation_id)

    # Check expiry
    age = datetime.now(timezone.utc) - rec.created_at
    if age > timedelta(days=RECOMMENDATION_MAX_AGE_DAYS):
        raise RecommendationExpiredError(
            recommendation_id, rec.created_at, RECOMMENDATION_MAX_AGE_DAYS
        )

    # Update product price
    product = await _get_product(db, rec.product_id)
    old_price = product.selling_price
    product.selling_price = rec.recommended_price

    # Create price history record
    price_history = PriceHistory(
        product_id=rec.product_id,
        old_unit_cost=product.unit_cost,
        new_unit_cost=product.unit_cost,
        old_selling_price=old_price,
        new_selling_price=rec.recommended_price,
        reason="AI pricing recommendation",
        effective_date=datetime.now(timezone.utc).date(),
        changed_by=user_id,
    )
    db.add(price_history)

    # Mark recommendation as applied
    now = datetime.now(timezone.utc)
    rec.status = RecommendationStatus.APPLIED
    rec.applied_at = now
    rec.applied_by = user_id

    await db.flush()

    await logger.ainfo(
        "pricing_recommendation_applied",
        recommendation_id=str(recommendation_id),
        product_id=str(rec.product_id),
        old_price=str(old_price),
        new_price=str(rec.recommended_price),
    )
    return rec


async def dismiss_recommendation(
    db: AsyncSession,
    recommendation_id: uuid.UUID,
) -> PricingRecommendation:
    """Dismiss a recommendation."""
    result = await db.execute(
        select(PricingRecommendation).where(
            PricingRecommendation.id == recommendation_id
        )
    )
    rec = result.scalar_one_or_none()
    if rec is None:
        raise RecommendationNotFoundError(recommendation_id)

    rec.status = RecommendationStatus.REJECTED
    await db.flush()
    return rec


# ---------------------------------------------------------------------------
# Cross-Subsidization Analysis
# ---------------------------------------------------------------------------


async def analyze_cross_subsidization(
    db: AsyncSession,
) -> CrossSubsidyAnalysis:
    """Analyze portfolio cross-subsidization patterns."""
    portfolio = await calculate_portfolio_margin(db)

    if len(portfolio["products"]) < 2:
        from src.pricing.exceptions import CrossSubsidyAnalysisError
        raise CrossSubsidyAnalysisError("Need at least 2 products with sales")

    high_margin = []
    low_margin = []

    for p in portfolio["products"]:
        entry = {
            "product_id": str(p["product_id"]),
            "product_name": p["product_name"],
            "margin_pct": p["margin_pct"],
            "revenue_30d": str(p["revenue_30d"]),
        }
        if p["margin_pct"] > 40:
            high_margin.append(entry)
        elif p["margin_pct"] < 34:
            low_margin.append(entry)

    recs = []
    for lm in low_margin:
        recs.append({
            "product_id": lm["product_id"],
            "action": "consider_price_increase",
            "reasoning": f"Margin {lm['margin_pct']}% below 35% target",
        })

    now = datetime.now(timezone.utc)
    analysis = CrossSubsidyAnalysis(
        analysis_date=now.date(),
        portfolio_total_margin=portfolio["blended_margin"],
        high_margin_products={"products": high_margin},
        low_margin_products={"products": low_margin},
        recommendations={"items": recs},
        created_at=now,
    )
    db.add(analysis)
    await db.flush()
    return analysis
