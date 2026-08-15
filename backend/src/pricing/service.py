"""Pricing domain service: demand forecasting, margin optimization, recommendations."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd
import structlog
from scipy.optimize import minimize
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.core.query_helpers import variant_or_untagged_filter
from src.fx.service import get_live_usdngn_rate
from src.orders.models import OrderLineItem, PurchaseOrder
from src.orders.service import get_order
from src.fx.exceptions import ForecastTimeoutError
from src.pricing.exceptions import (
    ElasticityNotFoundError,
    InsufficientPriceDataError,
    MarginTargetNotFoundError,
    MixTargetSumError,
    OptimizationInfeasibleError,
    PricingSuggestionError,
    RecommendationExpiredError,
    RecommendationNotFoundError,
)
from src.pricing.models import (
    CrossSubsidyAnalysis,
    DemandElasticity,
    MarginTarget,
    PriceSuggestion,
    PricingRecommendation,
    PricingScenario,
    ProductMixTarget,
    RecommendationStatus,
)
from src.products.models import PriceHistory, Product, ProductCategory, ProductVariant
from src.products.service import find_product_variant
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
    business_id: uuid.UUID | None = None,
    days: int = 180,
) -> pd.DataFrame:
    """Fetch daily aggregated sales for Prophet format."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    query = select(Sale.sale_date, func.sum(Sale.quantity)).where(
        Sale.product_id == product_id,
        Sale.status == SaleStatus.COMPLETED,
        Sale.sale_date >= cutoff.date(),
    )
    if business_id is not None:
        query = query.where(Sale.business_id == business_id)
    result = await db.execute(
        query.group_by(Sale.sale_date).order_by(Sale.sale_date.asc())
    )
    rows = result.all()

    if len(rows) < MIN_DATA_POINTS:
        raise InsufficientPriceDataError(product_id, len(rows), MIN_DATA_POINTS)

    df = pd.DataFrame([{"ds": row[0], "y": float(row[1])} for row in rows])  # financial-float-ok
    df["ds"] = pd.to_datetime(df["ds"])
    return df


def _train_demand_model(df: pd.DataFrame):  # -> Prophet (lazy-imported)
    """Train Prophet demand model (CPU-intensive)."""
    from prophet import Prophet  # lazy: keeps Prophet off the startup hot path

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
    model,
    horizon_days: int,  # model is a Prophet instance (lazy-imported type)
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
    business_id: uuid.UUID | None = None,
) -> dict:
    """Generate demand forecast with optional price elasticity adjustment."""
    df = await _fetch_sales_history(db, product_id, business_id=business_id)

    try:
        model = await asyncio.wait_for(
            asyncio.to_thread(_train_demand_model, df), timeout=30.0
        )
        forecast_df = await asyncio.wait_for(
            asyncio.to_thread(_generate_demand_forecast, model, horizon_days),
            timeout=30.0,
        )
    except asyncio.TimeoutError as e:
        raise ForecastTimeoutError("Prophet training", 30.0) from e

    # Apply price elasticity adjustment if proposed_price given
    multiplier = 1.0
    if proposed_price is not None:
        product = await _get_product(db, product_id, business_id=business_id)
        elasticity = await _get_elasticity_coefficient(db, product)
        price_change_pct = float(  # financial-float-ok
            (proposed_price - product.selling_price) / product.selling_price
        )
        multiplier = 1 + float(elasticity) * price_change_pct  # financial-float-ok

    forecasts = []
    total_demand = 0.0
    for _, row in forecast_df.iterrows():
        yhat = max(0, row["yhat"] * multiplier)
        lower = max(0, row["yhat_lower"] * multiplier)
        upper = max(0, row["yhat_upper"] * multiplier)
        total_demand += yhat
        forecasts.append(
            {
                "date": row["ds"].date(),
                "demand": round(yhat, 2),
                "demand_lower": round(lower, 2),
                "demand_upper": round(upper, 2),
            }
        )

    return {
        "product_id": product_id,
        "horizon_days": horizon_days,
        "forecasts": forecasts,
        "total_projected_demand": round(total_demand, 2),
    }


# ---------------------------------------------------------------------------
# Price Elasticity
# ---------------------------------------------------------------------------


DEFAULT_FX_SENSITIVITY = Decimal("0.0000")


async def _get_product(
    db: AsyncSession, product_id: uuid.UUID, business_id: uuid.UUID | None = None
) -> Product:
    """Fetch product or raise. Eager-loads category (+ its parent) since
    every caller may need it to resolve a category-default elasticity/FX
    sensitivity coefficient — ProductCategory.parent is lazy="raise", so
    this isn't optional (task 186).

    business_id, when provided, scopes the lookup to that tenant (task 204)
    -- without it any caller-supplied product_id from any business would
    resolve, regardless of who's asking.
    """
    query = (
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.category).selectinload(ProductCategory.parent))
    )
    if business_id is not None:
        query = query.where(Product.business_id == business_id)
    result = await db.execute(query)
    product = result.scalar_one_or_none()
    if product is None:
        from src.products.exceptions import ProductNotFoundError

        raise ProductNotFoundError(product_id)
    return product


def _resolve_elasticity_coefficient(
    product: Product, own: Decimal | None
) -> Decimal:
    """Own DemandElasticity value -> category default -> parent-category
    default -> system default (task 186, mirrors _resolve_target_margin's
    category-then-parent fallback)."""
    if own is not None:
        return own
    if product.category is not None:
        if product.category.default_elasticity_coefficient is not None:
            return product.category.default_elasticity_coefficient
        if (
            product.category.parent is not None
            and product.category.parent.default_elasticity_coefficient is not None
        ):
            return product.category.parent.default_elasticity_coefficient
    return DEFAULT_ELASTICITY


def _resolve_fx_sensitivity_coefficient(
    product: Product, own: Decimal | None
) -> Decimal:
    """Same fallback chain as _resolve_elasticity_coefficient, for FX
    sensitivity (task 186)."""
    if own is not None:
        return own
    if product.category is not None:
        if product.category.default_fx_sensitivity_coefficient is not None:
            return product.category.default_fx_sensitivity_coefficient
        if (
            product.category.parent is not None
            and product.category.parent.default_fx_sensitivity_coefficient is not None
        ):
            return product.category.parent.default_fx_sensitivity_coefficient
    return DEFAULT_FX_SENSITIVITY


async def _get_elasticity_coefficient(db: AsyncSession, product: Product) -> Decimal:
    """Get elasticity coefficient for a product: own configured value ->
    category default -> parent-category default -> system default
    (task 186)."""
    result = await db.execute(
        select(DemandElasticity).where(DemandElasticity.product_id == product.id)
    )
    elasticity = result.scalar_one_or_none()
    own = elasticity.elasticity_coefficient if elasticity else None
    return _resolve_elasticity_coefficient(product, own)


async def get_resolved_elasticity_config(
    db: AsyncSession, product_id: uuid.UUID, business_id: uuid.UUID | None = None
) -> dict:
    """Resolved elasticity + FX sensitivity coefficients for the config UI —
    always returns a value (own override, else category default, else
    system default) so the editor never starts blank (task 186, ST-802
    criterion 3). *_is_custom tells the UI whether this is the product's
    own saved override or an inherited default."""
    product = await _get_product(db, product_id, business_id=business_id)
    result = await db.execute(
        select(DemandElasticity).where(DemandElasticity.product_id == product_id)
    )
    elasticity = result.scalar_one_or_none()
    own_elasticity = elasticity.elasticity_coefficient if elasticity else None
    own_fx = elasticity.fx_sensitivity_coefficient if elasticity else None
    return {
        "product_id": product_id,
        "elasticity_coefficient": _resolve_elasticity_coefficient(
            product, own_elasticity
        ),
        "elasticity_is_custom": own_elasticity is not None,
        "fx_sensitivity_coefficient": _resolve_fx_sensitivity_coefficient(
            product, own_fx
        ),
        "fx_sensitivity_is_custom": own_fx is not None,
    }


async def calculate_price_elasticity_impact(
    db: AsyncSession,
    product_id: uuid.UUID,
    proposed_price: Decimal,
    business_id: uuid.UUID | None = None,
) -> dict:
    """Calculate demand impact for a proposed price change."""
    product = await _get_product(db, product_id, business_id=business_id)

    # E5 — Pricing floor: reject any proposed price at or below unit cost.
    # This mirrors the floor in compute_suggestion so that any user-submitted
    # price passes through the same loss-making guard before being used.
    if product.unit_cost is not None and proposed_price <= product.unit_cost:
        raise PricingSuggestionError(
            product_id,
            f"Proposed price {proposed_price} is at or below unit cost {product.unit_cost}. "
            "Cannot evaluate a loss-making price.",
        )

    elasticity = await _get_elasticity_coefficient(db, product)

    current_price = product.selling_price
    price_change_pct = float((proposed_price - current_price) / current_price)  # financial-float-ok
    demand_impact_pct = float(elasticity) * price_change_pct  # financial-float-ok

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
    db: AsyncSession, product_id: uuid.UUID, business_id: uuid.UUID | None = None
) -> DemandElasticity:
    """Get elasticity record for a product.

    DemandElasticity has no business_id column of its own -- ownership is
    verified via the product it belongs to before reading it (task 204).
    """
    if business_id is not None:
        await _get_product(db, product_id, business_id=business_id)
    result = await db.execute(
        select(DemandElasticity).where(DemandElasticity.product_id == product_id)
    )
    elasticity = result.scalar_one_or_none()
    if elasticity is None:
        raise ElasticityNotFoundError(product_id)
    return elasticity


async def update_elasticity_config(
    db: AsyncSession,
    product_id: uuid.UUID,
    coefficient: Decimal,
    fx_sensitivity_coefficient: Decimal | None = None,
    business_id: uuid.UUID | None = None,
) -> DemandElasticity:
    """Create or update elasticity (+ optional FX sensitivity) coefficient
    for a product. fx_sensitivity_coefficient=None leaves an existing saved
    value untouched rather than clobbering it (task 186).

    This is a write -- without verifying the product belongs to business_id,
    any authenticated user of any business could overwrite another
    business's product's elasticity/FX-sensitivity coefficients by
    product_id alone (task 204).
    """
    if business_id is not None:
        await _get_product(db, product_id, business_id=business_id)
    result = await db.execute(
        select(DemandElasticity).where(DemandElasticity.product_id == product_id)
    )
    elasticity = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if elasticity is None:
        elasticity = DemandElasticity(
            product_id=product_id,
            elasticity_coefficient=coefficient,
            fx_sensitivity_coefficient=fx_sensitivity_coefficient,
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
        if fx_sensitivity_coefficient is not None:
            elasticity.fx_sensitivity_coefficient = fx_sensitivity_coefficient
        elasticity.calculation_date = now.date()

    await db.flush()
    return elasticity


# ---------------------------------------------------------------------------
# Portfolio Margin
# ---------------------------------------------------------------------------


async def calculate_portfolio_margin(
    db: AsyncSession,
    target_margin: Decimal = DEFAULT_TARGET_MARGIN,
    business_id: uuid.UUID | None = None,
) -> dict:
    """Calculate blended portfolio margin and per-product breakdown.

    Blended margin is revenue-weighted from actual sales in the last 30 days.
    Per-product breakdown covers ALL active products:
    - Products with recent sales: actual (revenue − COGS) / revenue margin.
    - Products without recent sales: theoretical (selling_price − unit_cost) /
      selling_price margin, so they are never invisible to the user.

    When business_id is provided all queries are scoped to that tenant.
    """
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).date()

    # Build base filters for sales query
    sales_filters = [
        Product.is_active.is_(True),
        Sale.status == SaleStatus.COMPLETED,
        Sale.sale_date >= thirty_days_ago,
    ]
    if business_id is not None:
        sales_filters.append(Product.business_id == business_id)
        sales_filters.append(Sale.business_id == business_id)

    # Query 1: aggregate sales per product over the last 30 days (for blended margin)
    sales_result = await db.execute(
        select(
            Product.id,
            func.sum(Sale.quantity).label("qty"),
            func.sum(Sale.total_amount).label("revenue"),
        )
        .join(Sale, Sale.product_id == Product.id)
        .where(*sales_filters)
        .group_by(Product.id)
    )
    sales_by_product: dict = {
        pid: {"qty": qty, "revenue": revenue}
        for pid, qty, revenue in sales_result.all()
    }

    # Build base filters for products query
    products_filters = [Product.is_active.is_(True)]
    if business_id is not None:
        products_filters.append(Product.business_id == business_id)

    # Query 2: every active product (for the per-product table)
    all_products_result = await db.execute(
        select(
            Product.id,
            Product.name,
            Product.unit_cost,
            Product.selling_price,
        )
        .where(*products_filters)
        .order_by(Product.name)
    )

    products = []
    total_revenue = Decimal("0")
    total_cogs = Decimal("0")

    for pid, name, unit_cost, selling_price in all_products_result.all():
        sales = sales_by_product.get(pid)

        if sales:
            qty = sales["qty"]
            revenue = sales["revenue"]
            cogs = unit_cost * qty
            margin_pct = float((revenue - cogs) / revenue * 100) if revenue else 0.0  # financial-float-ok
            total_revenue += revenue
            total_cogs += cogs
        else:
            # No recent sales — show theoretical margin from current cost vs price
            qty = 0
            revenue = Decimal("0")
            cogs = Decimal("0")
            margin_pct = (
                float((selling_price - unit_cost) / selling_price * 100)  # financial-float-ok
                if selling_price > 0
                else 0.0
            )

        products.append(
            {
                "product_id": pid,
                "product_name": name,
                "unit_cost": unit_cost,
                "selling_price": selling_price,
                "margin_pct": round(margin_pct, 2),
                "revenue_30d": revenue,
                "cogs_30d": cogs,
                "quantity_30d": qty,
            }
        )

    blended_margin = (
        (total_revenue - total_cogs) / total_revenue * 100
        if total_revenue
        else Decimal("0")
    )

    blended_margin = blended_margin.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "blended_margin": blended_margin,
        "target_margin": target_margin,
        "margin_gap": (blended_margin - target_margin).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
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
    business_id: uuid.UUID,
) -> MarginTarget:
    """Create a margin target."""
    target = MarginTarget(
        business_id=business_id,
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


async def get_margin_targets(
    db: AsyncSession,
    business_id: uuid.UUID,
) -> list[MarginTarget]:
    """List all margin targets for the given business."""
    result = await db.execute(
        select(MarginTarget)
        .where(MarginTarget.business_id == business_id)
        .order_by(MarginTarget.priority.desc())
    )
    return list(result.scalars().all())


async def delete_margin_target(
    db: AsyncSession,
    target_id: uuid.UUID,
    business_id: uuid.UUID,
) -> None:
    """Delete a margin target — business-scoped so one business can't
    delete another's targets by guessing IDs."""
    result = await db.execute(
        select(MarginTarget).where(
            MarginTarget.id == target_id, MarginTarget.business_id == business_id
        )
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise MarginTargetNotFoundError(target_id)
    await db.delete(target)
    await db.flush()


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

    x0 = [float(p["selling_price"]) for p in products]  # financial-float-ok

    def _calc_totals(prices):
        total_rev = 0.0
        total_cogs = 0.0
        for i, p in enumerate(products):
            new_price = prices[i]
            old_price = float(p["selling_price"])  # financial-float-ok
            if old_price <= 0:
                continue
            price_change = (new_price - old_price) / old_price
            elasticity = float(p.get("elasticity", -1.0))  # financial-float-ok
            demand_mult = max(0.1, 1 + elasticity * price_change)
            projected_qty = float(p["avg_daily_sales"]) * 30 * demand_mult  # financial-float-ok
            total_rev += projected_qty * new_price
            total_cogs += projected_qty * float(p["unit_cost"])  # financial-float-ok
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
        (float(p["unit_cost"]) * 1.10, float(p["unit_cost"]) * 3.0) for p in products  # financial-float-ok
    ]

    constraints = [{"type": "ineq", "fun": margin_constraint}]

    result = minimize(
        objective,
        x0,
        bounds=bounds,
        method="SLSQP",
        constraints=constraints,
    )
    if not result.success:
        raise OptimizationInfeasibleError(result.message)

    optimized = []
    for i, p in enumerate(products):
        optimized.append(
            {
                "product_id": p["product_id"],
                "current_price": p["selling_price"],
                "optimized_price": Decimal(str(round(result.x[i], 2))),
                "unit_cost": p["unit_cost"],
            }
        )
    return optimized


# ---------------------------------------------------------------------------
# Pricing Recommendations
# ---------------------------------------------------------------------------


async def generate_recommendations(
    db: AsyncSession,
    business_id: uuid.UUID,
    target_margin: Decimal = DEFAULT_TARGET_MARGIN,
) -> list[PricingRecommendation]:
    """Generate pricing recommendations for products below target margin."""
    portfolio = await calculate_portfolio_margin(db, target_margin, business_id=business_id)

    # Get products below target margin
    below_target = [
        p for p in portfolio["products"] if p["margin_pct"] < float(target_margin)  # financial-float-ok
    ]

    if not below_target:
        await logger.ainfo(
            "pricing_no_recommendations_needed", margin=str(portfolio["blended_margin"])
        )
        return []

    # Prepare data for optimizer
    opt_inputs = []
    for p in below_target:
        product = await _get_product(db, p["product_id"])
        elasticity = await _get_elasticity_coefficient(db, product)
        avg_daily = p["quantity_30d"] / 30 if p["quantity_30d"] else 1
        opt_inputs.append(
            {
                "product_id": p["product_id"],
                "product_name": p["product_name"],
                "unit_cost": p["unit_cost"],
                "selling_price": p["selling_price"],
                "avg_daily_sales": avg_daily,
                "elasticity": float(elasticity),  # financial-float-ok
                "current_margin_pct": p["margin_pct"],
            }
        )

    # Run optimization in thread pool with a 30s timeout — minimize() can
    # hang indefinitely on certain degenerate input shapes.
    try:
        optimized = await asyncio.wait_for(
            asyncio.to_thread(
                _optimize_prices,
                opt_inputs,
                float(target_margin) / 100,  # financial-float-ok
            ),
            timeout=30.0,
        )
    except asyncio.TimeoutError as e:
        raise ForecastTimeoutError("SciPy price optimization", 30.0) from e
    except OptimizationInfeasibleError:
        return []

    # Create recommendations
    now = datetime.now(timezone.utc)
    recommendations: list[PricingRecommendation] = []

    for opt in optimized:
        current = Decimal(str(opt["current_price"]))
        recommended = opt["optimized_price"]
        unit_cost = Decimal(str(opt["unit_cost"]))

        if current == recommended:
            continue

        # E5 — Pricing floor: skip any recommendation below FIFO landed cost
        # Skip (don't raise) so other products' recommendations are still returned.
        if recommended < unit_cost:
            await logger.awarning(
                "pricing_recommendation_below_cost",
                product_id=str(opt["product_id"]),
                recommended=str(recommended),
                unit_cost=str(unit_cost),
            )
            continue  # Skip this product; never recommend a loss-making price

        price_change_pct = float((recommended - current) / current * 100)  # financial-float-ok
        opt_product = await _get_product(db, opt["product_id"])
        elasticity = await _get_elasticity_coefficient(db, opt_product)
        demand_change = float(elasticity) * price_change_pct / 100  # financial-float-ok

        # Estimate margin improvement
        new_margin = float((recommended - opt["unit_cost"]) / recommended * 100)  # financial-float-ok
        margin_change = new_margin - float((current - opt["unit_cost"]) / current * 100)  # financial-float-ok

        # Determine priority
        margin_gap = float(target_margin) - float(  # financial-float-ok
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
            f"demand impact (elasticity: {float(elasticity):.2f})."  # financial-float-ok
        )

        rec = PricingRecommendation(
            business_id=business_id,
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
    business_id: uuid.UUID,
) -> list[PricingRecommendation]:
    """Get all pending recommendations for the given business."""
    result = await db.execute(
        select(PricingRecommendation)
        .where(
            PricingRecommendation.business_id == business_id,
            PricingRecommendation.status == RecommendationStatus.PENDING,
        )
        .order_by(PricingRecommendation.created_at.desc())
    )
    return list(result.scalars().all())


async def apply_recommendation(
    db: AsyncSession,
    recommendation_id: uuid.UUID,
    user_id: uuid.UUID,
    business_id: uuid.UUID,
) -> PricingRecommendation:
    """Apply a pricing recommendation: update product price."""
    result = await db.execute(
        select(PricingRecommendation).where(
            PricingRecommendation.id == recommendation_id,
            PricingRecommendation.business_id == business_id,
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
    business_id: uuid.UUID,
) -> PricingRecommendation:
    """Dismiss a recommendation."""
    result = await db.execute(
        select(PricingRecommendation).where(
            PricingRecommendation.id == recommendation_id,
            PricingRecommendation.business_id == business_id,
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
    business_id: uuid.UUID | None = None,
) -> CrossSubsidyAnalysis:
    """Analyze portfolio cross-subsidization patterns.

    A read, not a write: this is a GET endpoint, so the returned analysis is
    computed fresh on every call and never persisted -- it previously
    inserted a new CrossSubsidyAnalysis row on every request, which has no
    consumer (nothing reads analysis history back) and would grow the table
    unboundedly. `id`/`created_at` are still populated (not DB defaults) so
    CrossSubsidyRead can serialize the result as if it were a stored row.
    """
    portfolio = await calculate_portfolio_margin(db, business_id=business_id)

    if len(portfolio["products"]) < 2:
        from src.pricing.exceptions import CrossSubsidyAnalysisError

        raise CrossSubsidyAnalysisError("Need at least 2 products with sales")

    # Bucketed relative to the business's actual target margin, not a
    # hardcoded 40%/34% that only coincidentally matched the module default
    # of 35% -- a product at 48% margin is "high" against a 35% target but
    # below-target (and should offer no subsidy) against a 50% target.
    target_margin = portfolio["target_margin"]
    high_threshold = target_margin + 5
    low_threshold = target_margin - 1

    high_margin = []
    low_margin = []

    for p in portfolio["products"]:
        entry = {
            "product_id": str(p["product_id"]),
            "product_name": p["product_name"],
            "margin_pct": p["margin_pct"],
            "revenue_30d": str(p["revenue_30d"]),
        }
        if p["margin_pct"] > high_threshold:
            high_margin.append(entry)
        elif p["margin_pct"] < low_threshold:
            low_margin.append(entry)

    recs = []
    for lm in low_margin:
        recs.append(
            {
                "product_id": lm["product_id"],
                "action": "consider_price_increase",
                "reasoning": f"Margin {lm['margin_pct']}% below {target_margin}% target",
            }
        )

    now = datetime.now(timezone.utc)
    return CrossSubsidyAnalysis(
        id=uuid.uuid4(),
        analysis_date=now.date(),
        portfolio_total_margin=portfolio["blended_margin"],
        high_margin_products={"products": high_margin},
        low_margin_products={"products": low_margin},
        recommendations={"items": recs},
        created_at=now,
    )


# ---------------------------------------------------------------------------
# Product Mix Targets
# ---------------------------------------------------------------------------

MIX_DRIFT_THRESHOLD = Decimal("5.00")


async def upsert_mix_targets(
    db: AsyncSession,
    targets: list[dict],
    business_id: uuid.UUID | None = None,
) -> list[ProductMixTarget]:
    """Bulk upsert product-mix targets. Sum of target_pct must equal 100."""
    total = sum(Decimal(str(t["target_pct"])) for t in targets)
    if total != Decimal("100"):
        raise MixTargetSumError(total)

    result_targets: list[ProductMixTarget] = []
    for t in targets:
        category_id = t["category_id"]
        target_pct = Decimal(str(t["target_pct"]))

        lookup_filters = [ProductMixTarget.category_id == category_id]
        if business_id is not None:
            lookup_filters.append(ProductMixTarget.business_id == business_id)

        result = await db.execute(
            select(ProductMixTarget).where(*lookup_filters)
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            existing.target_pct = target_pct
            result_targets.append(existing)
        else:
            new_target = ProductMixTarget(
                category_id=category_id,
                target_pct=target_pct,
                **({"business_id": business_id} if business_id is not None else {}),
            )
            db.add(new_target)
            result_targets.append(new_target)

    await db.flush()

    await logger.ainfo(
        "mix_targets_upserted",
        count=len(result_targets),
        total_pct=str(total),
    )
    return result_targets


async def get_mix_status(
    db: AsyncSession,
    days: int = 90,
    business_id: uuid.UUID | None = None,
) -> list[dict]:
    """Compare actual revenue % by category against mix targets."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date()

    # Build filters for revenue query
    mix_filters = [
        Sale.status == SaleStatus.COMPLETED,
        Sale.sale_date >= cutoff,
    ]
    if business_id is not None:
        mix_filters.append(Sale.business_id == business_id)
        mix_filters.append(Product.business_id == business_id)

    # Get actual revenue per category
    result = await db.execute(
        select(
            ProductCategory.id,
            ProductCategory.name,
            func.coalesce(func.sum(Sale.total_amount), Decimal("0")).label(
                "category_revenue"
            ),
        )
        .join(Product, Product.category_id == ProductCategory.id)
        .join(Sale, Sale.product_id == Product.id)
        .where(*mix_filters)
        .group_by(ProductCategory.id, ProductCategory.name)
    )
    revenue_rows = result.all()

    total_revenue = sum(row[2] for row in revenue_rows)

    # Get targets scoped to the business
    target_filters = []
    if business_id is not None:
        target_filters.append(ProductMixTarget.business_id == business_id)
    target_result = await db.execute(
        select(ProductMixTarget).where(*target_filters) if target_filters else select(ProductMixTarget)
    )
    targets = {t.category_id: t.target_pct for t in target_result.scalars().all()}

    statuses: list[dict] = []
    for cat_id, cat_name, cat_revenue in revenue_rows:
        actual_pct = (
            (cat_revenue / total_revenue * Decimal("100"))
            if total_revenue > 0
            else Decimal("0")
        )
        target_pct = targets.get(cat_id, Decimal("0"))
        variance_pct = actual_pct - target_pct

        statuses.append(
            {
                "category_id": cat_id,
                "category_name": cat_name,
                "actual_pct": actual_pct.quantize(Decimal("0.01")),
                "target_pct": target_pct,
                "variance_pct": variance_pct.quantize(Decimal("0.01")),
            }
        )

    # Include categories with targets but no revenue
    seen_ids = {s["category_id"] for s in statuses}
    for cat_id, target_pct in targets.items():
        if cat_id not in seen_ids:
            # Look up category name
            cat_result = await db.execute(
                select(ProductCategory.name).where(ProductCategory.id == cat_id)
            )
            cat_name = cat_result.scalar_one_or_none() or "Unknown"
            statuses.append(
                {
                    "category_id": cat_id,
                    "category_name": cat_name,
                    "actual_pct": Decimal("0.00"),
                    "target_pct": target_pct,
                    "variance_pct": (Decimal("0") - target_pct).quantize(
                        Decimal("0.01")
                    ),
                }
            )

    return statuses


async def check_mix_drift_alert(db: AsyncSession, business_id: uuid.UUID | None = None) -> None:
    """Create INVENTORY AI recommendation if any category drifts > 5%."""
    from src.ai_engine.models import (
        AIRecommendation,
        ActionType,
        RecommendationCategory,
        RecommendationPriority,
        RecommendationStatus as AIRecommendationStatus,
    )

    statuses = await get_mix_status(db, business_id=business_id)
    drifted = [s for s in statuses if abs(s["variance_pct"]) > MIX_DRIFT_THRESHOLD]

    if not drifted:
        return

    # Dedup: check for existing pending mix-drift recommendation
    result = await db.execute(
        select(AIRecommendation).where(
            AIRecommendation.category == RecommendationCategory.INVENTORY,
            AIRecommendation.reference_type == "mix_drift",
            AIRecommendation.status == AIRecommendationStatus.PENDING,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        await logger.ainfo("mix_drift_alert_already_exists", rec_id=str(existing.id))
        return

    drift_details = "; ".join(
        f"{s['category_name']}: {s['variance_pct']:+}% (actual {s['actual_pct']}% vs target {s['target_pct']}%)"
        for s in drifted
    )

    now = datetime.now(timezone.utc)
    rec = AIRecommendation(
        category=RecommendationCategory.INVENTORY,
        title="Product mix drift detected",
        description=(
            f"The following categories have drifted more than "
            f"{MIX_DRIFT_THRESHOLD}% from target: {drift_details}"
        ),
        priority=RecommendationPriority.MEDIUM,
        confidence=Decimal("80.00"),
        action_type=ActionType.REORDER,
        reference_type="mix_drift",
        status=AIRecommendationStatus.PENDING,
        created_at=now,
        expires_at=now + timedelta(days=30),
    )
    db.add(rec)
    await db.flush()

    await logger.ainfo(
        "mix_drift_alert_created",
        drifted_count=len(drifted),
        rec_id=str(rec.id),
    )


# ---------------------------------------------------------------------------
# Price-FX Sensitivity Playground
# ---------------------------------------------------------------------------

MAX_SAVED_SCENARIOS = 10


async def sensitivity_calc(
    db: AsyncSession,
    selling_price: Decimal,
    fx_rate: Decimal,
    quantity: int,
    product_id: uuid.UUID | None = None,
    unit_cost_usd_override: Decimal | None = None,
    business_id: uuid.UUID | None = None,
) -> dict:
    """Stateless price-FX sensitivity calculation.

    Uses FIFO batches to get landed cost when a product_id is supplied,
    otherwise requires unit_cost_usd_override.
    """
    from src.inventory.service import get_batches_for_product

    unit_cost_usd: Decimal

    if product_id is not None:
        # Try to get FIFO batch cost from inventory
        batches = await get_batches_for_product(db, product_id, business_id=business_id)
        active_batches = [b for b in batches if b.quantity_remaining > 0]
        if active_batches:
            # Use the weighted-average unit cost from active batches
            unit_cost_usd = active_batches[0].unit_cost_usd
        else:
            # Fall back to the product's unit_cost
            product = await _get_product(db, product_id, business_id=business_id)
            unit_cost_usd = product.unit_cost

    if unit_cost_usd_override is not None:
        unit_cost_usd = unit_cost_usd_override

    if product_id is None and unit_cost_usd_override is None:
        raise ValueError("Either product_id or unit_cost_usd must be provided")

    landed_cost_ngn = (unit_cost_usd * fx_rate).quantize(Decimal("0.000001"))

    margin_pct = Decimal("0")
    if selling_price > 0:
        margin_pct = (
            (selling_price - landed_cost_ngn) / selling_price * Decimal("100")
        ).quantize(Decimal("0.01"))

    total_revenue = selling_price * Decimal(str(quantity))
    total_cost = landed_cost_ngn * Decimal(str(quantity))
    gross_profit = total_revenue - total_cost

    return {
        "unit_cost_usd": unit_cost_usd,
        "fx_rate": fx_rate,
        "landed_cost_ngn": landed_cost_ngn,
        "selling_price": selling_price,
        "margin_pct": margin_pct,
        "quantity": quantity,
        "total_revenue": total_revenue,
        "total_cost": total_cost,
        "gross_profit": gross_profit,
    }


async def save_scenario(
    db: AsyncSession,
    name: str,
    user_id: uuid.UUID,
    business_id: uuid.UUID,
    selling_price: Decimal,
    fx_rate: Decimal,
    quantity: int,
    product_id: uuid.UUID | None = None,
    results: dict | None = None,
) -> PricingScenario:
    """Save a pricing scenario (max 10 per user per business, archive oldest)."""
    # Count existing scenarios for user within this business
    count_result = await db.execute(
        select(func.count(PricingScenario.id)).where(
            PricingScenario.business_id == business_id,
            PricingScenario.created_by == user_id,
        )
    )
    count = count_result.scalar() or 0

    if count >= MAX_SAVED_SCENARIOS:
        # Delete the oldest scenarios to make room
        excess = count - MAX_SAVED_SCENARIOS + 1
        oldest_result = await db.execute(
            select(PricingScenario)
            .where(
                PricingScenario.business_id == business_id,
                PricingScenario.created_by == user_id,
            )
            .order_by(PricingScenario.created_at.asc())
            .limit(excess)
        )
        oldest_scenarios = list(oldest_result.scalars().all())
        for old in oldest_scenarios:
            await db.delete(old)

    now = datetime.now(timezone.utc)
    scenario = PricingScenario(
        business_id=business_id,
        name=name,
        product_id=product_id,
        selling_price=selling_price,
        fx_rate=fx_rate,
        quantity=quantity,
        results=results,
        created_by=user_id,
        created_at=now,
    )
    db.add(scenario)
    await db.flush()

    await logger.ainfo(
        "pricing_scenario_saved",
        scenario_id=str(scenario.id),
        name=name,
        user_id=str(user_id),
        business_id=str(business_id),
    )
    return scenario


async def list_scenarios(
    db: AsyncSession,
    user_id: uuid.UUID,
    business_id: uuid.UUID,
) -> list[PricingScenario]:
    """List saved scenarios for a user within the given business, newest first."""
    result = await db.execute(
        select(PricingScenario)
        .where(
            PricingScenario.business_id == business_id,
            PricingScenario.created_by == user_id,
        )
        .order_by(PricingScenario.created_at.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Selling Price Suggestion (FX-aware)
# ---------------------------------------------------------------------------


async def get_selling_price_suggestion(
    db: AsyncSession,
    product_id: uuid.UUID | None,
    unit_cost_override: Decimal | None,
    currency: str,
    fx_rate_override: Decimal | None,
    min_margin_pct: Decimal,
    business_id: uuid.UUID | None = None,
) -> dict:
    """Compute the minimum recommended selling price in NGN.

    If currency is not NGN, the unit_cost is treated as being in that
    foreign currency and is converted to NGN using the current USDNGN FX rate
    (or the provided fx_rate_override). The minimum selling price is then:

        min_price = unit_cost_ngn / (1 - min_margin_pct / 100)

    ensuring the gross margin never falls below the specified threshold.
    """
    if min_margin_pct >= Decimal("100"):
        raise ValueError("min_margin_pct must be less than 100")

    unit_cost: Decimal
    resolved_currency: str

    if product_id is not None:
        product = await _get_product(db, product_id, business_id=business_id)
        unit_cost = product.unit_cost
        resolved_currency = product.currency
    else:
        if unit_cost_override is None:
            raise ValueError("Either product_id or unit_cost_override must be provided")
        unit_cost = unit_cost_override
        resolved_currency = currency

    fx_rate_stale = False
    fx_rate_source = "live"

    if resolved_currency == "NGN":
        fx_rate = Decimal("1")
        unit_cost_ngn = unit_cost
        fx_rate_source = "ngn"
    else:
        if fx_rate_override is not None:
            fx_rate = fx_rate_override
            fx_rate_source = "override"
        else:
            from src.fx.service import get_current_rate as _get_fx_rate

            pair = f"{resolved_currency}NGN"
            rate_record = await _get_fx_rate(db, pair)
            fx_rate = rate_record.rate
            age_seconds = (
                datetime.now(timezone.utc) - rate_record.timestamp
            ).total_seconds()
            fx_rate_stale = age_seconds > settings.FX_CACHE_TTL_HOURS * 3600
            fx_rate_source = rate_record.source.value if not fx_rate_stale else "cached"
        unit_cost_ngn = (unit_cost * fx_rate).quantize(Decimal("0.000001"))

    margin_factor = Decimal("1") - (min_margin_pct / Decimal("100"))
    min_selling_price = (unit_cost_ngn / margin_factor).quantize(Decimal("0.000001"))

    return {
        "unit_cost": unit_cost,
        "currency": resolved_currency,
        "fx_rate": fx_rate,
        "unit_cost_ngn": unit_cost_ngn,
        "min_margin_pct": min_margin_pct,
        "min_selling_price": min_selling_price,
        "fx_rate_stale": fx_rate_stale,
        "fx_rate_source": fx_rate_source,
    }


# ---------------------------------------------------------------------------
# Lot-based price suggestion engine (Task #76)
# ---------------------------------------------------------------------------


def _pick_margin_target(
    margin_targets: list[MarginTarget], product: Product | None
) -> MarginTarget | None:
    """Most-specific-wins: a product-level MarginTarget beats a
    category-level one regardless of priority — priority only breaks ties
    among rows at the SAME specificity (e.g. two product-level rows for
    the same product). Returns the whole matched row (both
    target_margin_pct and min_margin_pct come from it) or None if no
    MarginTarget applies."""
    if product is None:
        return None

    product_rows = sorted(
        (t for t in margin_targets if t.product_id == product.id),
        key=lambda t: t.priority,
        reverse=True,
    )
    if product_rows:
        return product_rows[0]

    category_ids = []
    if product.category_id is not None:
        category_ids.append(product.category_id)
    if product.category is not None and product.category.parent_id is not None:
        category_ids.append(product.category.parent_id)
    category_rows = sorted(
        (t for t in margin_targets if t.category_id in category_ids),
        key=lambda t: t.priority,
        reverse=True,
    )
    if category_rows:
        return category_rows[0]

    return None


def _resolve_target_margin(
    product: Product | None, margin_targets: list[MarginTarget] | None = None
) -> Decimal:
    """Settings-configured MarginTarget (product → category → parent
    category) → ProductCategory.default_margin_pct (sub-category →
    parent) → system default (40%). Shared by every price-suggestion path
    so they can't drift out of sync."""
    picked = _pick_margin_target(margin_targets or [], product)
    if picked is not None:
        return picked.target_margin_pct / Decimal("100")
    if product and product.category:
        if product.category.default_margin_pct is not None:
            return product.category.default_margin_pct
        if (
            product.category.parent is not None
            and product.category.parent.default_margin_pct is not None
        ):
            return product.category.parent.default_margin_pct
    return Decimal("0.40")


def _resolve_min_margin(
    product: Product | None, margin_targets: list[MarginTarget] | None = None
) -> Decimal | None:
    """The Settings-configured MarginTarget's min_margin_pct (0-1 fraction)
    for this product/category, or None if no MarginTarget applies — there
    is no category-default equivalent for a minimum, so unlike
    _resolve_target_margin() this has no further fallback. Applied by
    callers as a floor on the computed suggested_price, since a target
    margin resolved from a category default could otherwise undercut a
    business's explicitly configured minimum."""
    picked = _pick_margin_target(margin_targets or [], product)
    if picked is None:
        return None
    return picked.min_margin_pct / Decimal("100")


def _apply_min_margin_floor(
    suggested_price: Decimal, cost_ngn: Decimal, min_margin: Decimal | None
) -> Decimal:
    """Bump suggested_price up to the min-margin price if it would
    otherwise fall below the configured floor. No-op when min_margin is
    None (nothing configured) or >= 100% (nonsensical, ignored rather than
    dividing by zero/negative)."""
    if min_margin is None:
        return suggested_price
    min_margin_factor = Decimal("1") - min_margin
    if min_margin_factor <= 0:
        return suggested_price
    min_price = (cost_ngn / min_margin_factor).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )
    return max(suggested_price, min_price)


async def _fetch_margin_targets(
    db: AsyncSession,
    business_id: uuid.UUID | None,
    product_ids: set[uuid.UUID],
    category_ids: set[uuid.UUID],
) -> list[MarginTarget]:
    """Batch-fetch every MarginTarget row that could apply to the given
    products/categories, in one query — callers resolve per-item via
    _resolve_target_margin() instead of querying per line item."""
    if business_id is None or (not product_ids and not category_ids):
        return []
    conditions = []
    if product_ids:
        conditions.append(MarginTarget.product_id.in_(product_ids))
    if category_ids:
        conditions.append(MarginTarget.category_id.in_(category_ids))
    result = await db.execute(
        select(MarginTarget).where(
            MarginTarget.business_id == business_id, or_(*conditions)
        )
    )
    return list(result.scalars().all())


async def compute_suggestion(
    db: AsyncSession,
    product_id: uuid.UUID,
    target_margin: Decimal | None = None,
    variant_id: uuid.UUID | None = None,
    business_id: uuid.UUID | None = None,
) -> "PriceSuggestion":  # noqa: F821 — forward ref resolved at runtime
    """Compute and persist a sell-price suggestion from active lot cost basis.

    Weighted-average unit_cost_ngn across all lots with units_remaining > 0.
    Lots without unit_cost_ngn are costed at unit_cost * live FX rate.
    When target_margin is None, resolves from: sub-category → parent → 40% default.

    variant_id scopes which lots are eligible via variant_or_untagged_filter()
    (src/core/query_helpers.py) — the same cross-variant pooling bug task 165
    fixed for fifo_deduct() and task 168 fixed for _deduct_lot_units(), on
    this third units_remaining consumer (task 171). Omitting it (the
    default) preserves prior behaviour for non-variant products.
    """
    # A variant_id belonging to a different product (or an inactive one)
    # must be rejected up front — before the lot query, and before the
    # live FX-rate fetch below (which can hit an external API and persist
    # a new FXRate row on a cache miss). Checking first avoids paying for
    # both on a request that's going to fail validation anyway.
    variant: ProductVariant | None = None
    if variant_id is not None:
        variant = await find_product_variant(db, variant_id, product_id)
        if variant is None:
            raise PricingSuggestionError(
                product_id,
                f"variant {variant_id} does not belong to this product, or is inactive",
            )

    # Fetch active lots joined with their parent order's currency.
    # variant_id=None (the default) intentionally does NOT filter by
    # variant at all — unlike fifo_deduct()/_deduct_lot_units(), where a
    # None variant_id means "this really is a non-variant sale" (enforced
    # upfront by create_sale()), a caller here may simply not know/care
    # about variant scoping (e.g. the existing products-page.component.ts
    # "suggest price" button, which never passes variant_id). Pooling
    # across every variant is this function's original, still-supported
    # behaviour for that case. Only an explicit variant_id narrows the
    # query, via variant_or_untagged_filter() (own variant + untagged,
    # never a sibling's — task 165's rule).
    where_clauses = [
        OrderLineItem.product_id == product_id,
        OrderLineItem.units_remaining > 0,
    ]
    if variant_id is not None:
        where_clauses.append(
            variant_or_untagged_filter(OrderLineItem.variant_id, variant_id)
        )
    if business_id is not None:
        where_clauses.append(PurchaseOrder.business_id == business_id)
    lot_result = await db.execute(
        select(OrderLineItem, PurchaseOrder.currency)
        .join(PurchaseOrder, OrderLineItem.order_id == PurchaseOrder.id)
        .where(*where_clauses)
    )
    lots_with_currency = lot_result.all()

    if not lots_with_currency:
        raise PricingSuggestionError(
            product_id, "no active lots with units_remaining > 0"
        )

    # Get live FX rate (used as fallback for USD lots without unit_cost_ngn)
    fx_rate, _, _ = await get_live_usdngn_rate(db)

    # Weighted-average landed cost (currency-aware fallback)
    total_cost = Decimal("0")
    total_units = Decimal("0")
    for lot, order_currency in lots_with_currency:
        if lot.unit_cost_ngn is not None:
            cost_ngn = lot.unit_cost_ngn
        elif order_currency == "USD":
            cost_ngn = lot.unit_cost * fx_rate
        else:
            cost_ngn = lot.unit_cost
        total_cost += cost_ngn * lot.units_remaining
        total_units += lot.units_remaining

    avg_cost_ngn = (total_cost / total_units).quantize(Decimal("0.000001"))

    # Load product with category + parent for margin resolution and catalog price
    product_where = [Product.id == product_id]
    if business_id is not None:
        product_where.append(Product.business_id == business_id)
    prod_result = await db.execute(
        select(Product)
        .options(selectinload(Product.category).selectinload(ProductCategory.parent))
        .where(*product_where)
    )
    product = prod_result.scalar_one_or_none()

    # Resolve effective margin: caller override → MarginTarget (Settings) →
    # sub-category → parent → system default. margin_targets is fetched
    # unconditionally (not just when target_margin is None) because
    # min_margin_pct — a floor applied below — is a business policy that
    # should hold even when the caller supplied their own target_margin.
    category_ids: set[uuid.UUID] = set()
    if product and product.category_id is not None:
        category_ids.add(product.category_id)
    if (
        product
        and product.category is not None
        and product.category.parent_id is not None
    ):
        category_ids.add(product.category.parent_id)
    margin_targets = await _fetch_margin_targets(
        db, business_id, product_ids={product_id}, category_ids=category_ids
    )
    if target_margin is None:
        target_margin = _resolve_target_margin(product, margin_targets)

    # Suggested price
    margin_factor = Decimal("1") - target_margin
    suggested_price = (avg_cost_ngn / margin_factor).quantize(Decimal("0.000001"))
    suggested_price = _apply_min_margin_floor(
        suggested_price, avg_cost_ngn, _resolve_min_margin(product, margin_targets)
    )

    # E5 — Pricing floor: never return a price at or below FIFO landed cost.
    # Note: the formula avg_cost_ngn / (1 - target_margin) always produces a
    # value above avg_cost_ngn when target_margin ∈ (0, 1), so this guard
    # catches edge cases where target_margin is 0 (break-even) or rounding
    # produces an exact match — both represent zero-margin or loss-making prices.
    if suggested_price <= avg_cost_ngn:
        raise PricingSuggestionError(
            product_id,
            f"Suggested price {suggested_price} is at or below FIFO landed cost {avg_cost_ngn}. "
            "Cannot recommend a loss-making price.",
        )

    # Catalog price for context — the variant's own price_override, if
    # set, otherwise the product's base selling_price. Mirrors every other
    # variant-aware price resolver (products/service.py, sales/service.py,
    # orders/service.py).
    catalog_price: Decimal | None = None
    if variant is not None and variant.price_override is not None:
        catalog_price = variant.price_override
    elif product:
        catalog_price = product.selling_price

    suggestion = PriceSuggestion(
        product_id=product_id,
        variant_id=variant_id,
        unit_cost_ngn=avg_cost_ngn,
        fx_rate_used=fx_rate,
        target_margin_pct=target_margin,
        suggested_price_ngn=suggested_price,
        current_catalog_price_ngn=catalog_price,
        suggested_at=datetime.now(timezone.utc),
    )
    db.add(suggestion)
    await db.flush()

    await logger.ainfo(
        "price_suggestion_computed",
        product_id=str(product_id),
        suggested_price=str(suggested_price),
        fx_rate=str(fx_rate),
        margin=str(target_margin),
    )
    return suggestion


async def suggest_prices_for_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> dict:
    """Per-line-item selling-price suggestions for a purchase order.

    Unlike compute_suggestion() (lot-based, requires units_remaining > 0 —
    i.e. the order must already be DELIVERED), this costs directly off the
    order's own line items, so it works at any status, including before
    delivery. Always uses the LIVE current FX rate (not the order's own
    booked fx_rate_at_creation/fx_rate_at_delivery) — the point is "what
    would I price this at today", not "what did it cost historically".

    Same shipping/clearing logistics-per-unit formula as
    transition_status()'s DELIVERED handling and correct_delivered_order_
    costs() (orders/service.py), and the same MarginTarget → category →
    parent → 40% margin resolution as compute_suggestion(), via
    _resolve_target_margin() — MarginTarget rows are batch-fetched once
    for the whole order rather than per line item.
    """
    order = await get_order(db, order_id, business_id)

    fx_rate, _, _ = await get_live_usdngn_rate(db)

    total_logistics = (order.shipping_cost or Decimal("0")) + (
        order.clearing_cost or Decimal("0")
    )
    total_units = sum(li.quantity for li in order.line_items) or 1
    logistics_per_unit = (total_logistics / Decimal(str(total_units))).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )

    product_ids = {li.product_id for li in order.line_items}
    products_by_id: dict[uuid.UUID, Product] = {}
    if product_ids:
        prod_result = await db.execute(
            select(Product)
            .options(selectinload(Product.category).selectinload(ProductCategory.parent))
            .where(Product.id.in_(product_ids))
        )
        products_by_id = {p.id: p for p in prod_result.scalars().all()}

    category_ids: set[uuid.UUID] = set()
    for p in products_by_id.values():
        if p.category_id is not None:
            category_ids.add(p.category_id)
        if p.category is not None and p.category.parent_id is not None:
            category_ids.add(p.category.parent_id)
    margin_targets = await _fetch_margin_targets(
        db, business_id, product_ids=product_ids, category_ids=category_ids
    )

    items = []
    for li in order.line_items:
        if li.unit_cost_ngn is not None:
            cost_ngn = li.unit_cost_ngn
        elif order.currency == "USD":
            cost_ngn = li.unit_cost * fx_rate
        else:
            cost_ngn = li.unit_cost
        landed_cost_ngn = (cost_ngn + logistics_per_unit).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )

        product = products_by_id.get(li.product_id)
        target_margin = _resolve_target_margin(product, margin_targets)
        margin_factor = Decimal("1") - target_margin
        suggested_price = (
            (landed_cost_ngn / margin_factor).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )
            if margin_factor > 0
            else None
        )
        if suggested_price is not None:
            suggested_price = _apply_min_margin_floor(
                suggested_price, landed_cost_ngn, _resolve_min_margin(product, margin_targets)
            )

        items.append(
            {
                "line_item_id": li.id,
                "product_id": li.product_id,
                "product_name": product.name if product else "",
                "unit_cost_ngn": landed_cost_ngn,
                "current_price_ngn": product.selling_price if product else None,
                "target_margin_pct": target_margin,
                "suggested_price_ngn": suggested_price,
            }
        )

    return {"order_id": order.id, "fx_rate_used": fx_rate, "items": items}


async def get_suggestion_history(
    db: AsyncSession,
    product_id: uuid.UUID,
    limit: int = 30,
    variant_id: uuid.UUID | None = None,
    business_id: uuid.UUID | None = None,
) -> list:
    """Return the last `limit` price suggestions for a product, newest
    first.

    variant_id narrows to suggestions computed for exactly that variant —
    omitting it (the default) preserves prior behaviour: every suggestion
    for the product, regardless of which variant (or none) it was for.
    Without this, a product's variants' suggestion histories interleave
    with no way to tell them apart (task 171).

    PriceSuggestion has no business_id column of its own -- business_id,
    when provided, verifies the product belongs to that tenant before
    reading its suggestion history (task 204).

    Raises PricingSuggestionError if variant_id doesn't belong to
    product_id — a mismatched pair would otherwise just silently return
    an empty list, masking a client-side bug that passed the wrong pair.
    Deliberately does NOT filter by is_active like compute_suggestion()
    does: a deactivated variant's *past* suggestions should stay visible
    (this is a history read, not a request to compute a new suggestion
    against that variant's current, possibly-gone lot stock)."""
    if business_id is not None:
        await _get_product(db, product_id, business_id=business_id)
    if variant_id is not None:
        variant = await find_product_variant(
            db, variant_id, product_id, active_only=False
        )
        if variant is None:
            raise PricingSuggestionError(
                product_id, f"variant {variant_id} does not belong to this product"
            )

    where_clauses = [PriceSuggestion.product_id == product_id]
    if variant_id is not None:
        where_clauses.append(PriceSuggestion.variant_id == variant_id)

    result = await db.execute(
        select(PriceSuggestion)
        .where(*where_clauses)
        .order_by(PriceSuggestion.suggested_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())

