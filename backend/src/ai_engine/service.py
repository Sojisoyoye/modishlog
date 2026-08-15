"""AI Engine service: unified recommendations, USD accumulation, reorder suggestions."""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_engine.exceptions import (
    RecommendationAlreadyProcessedError,
    RecommendationExpiredError,
    RecommendationNotFoundError,
    ReorderSuggestionNotFoundError,
    USDStrategyConfigNotFoundError,
)
from src.ai_engine.models import (
    AIRecommendation,
    ActionType,
    RecommendationCategory,
    RecommendationPriority,
    RecommendationStatus,
    ReorderConfig,
    ReorderStatus,
    ReorderSuggestion,
    RiskTolerance,
    USDStrategyConfig,
)
from src.cashflow.models import LoanObligation, LoanStatus
from src.core.ai_safety import contains_pii_check  # noqa: F401  re-exported; E6 PII guard
from src.inventory.models import MovementType, StockMovement
from src.inventory.service import inventory_on_hand_by_product_subquery
from src.orders.models import (
    OrderPayment,
    OrderStatus,
    PaymentStatus,
    PurchaseOrder,
)
from src.products.models import Product
from src.sales.models import Sale, SaleStatus

logger = structlog.get_logger()

RECOMMENDATION_EXPIRY_DAYS = 30
DEFAULT_FX_RATE = Decimal("1500.000000")
DEFAULT_LEAD_TIME_DAYS = 30
SAFETY_STOCK_MULTIPLIER = Decimal("1.50")

# E1 — Minimum data points for a reliable model
MIN_RELIABLE_DATA_POINTS = 30
UNDER_TRAINED_DISCLAIMER = (
    "Recommendation is based on limited historical data (<30 data points). "
    "Treat with caution and validate against your own business knowledge."
)

# E4 — High-consequence action types that require human review
# These must match ActionType enum .value strings (see ai_engine/models.py).
# fx_lock commits FX capital; usd_purchase is a large USD commitment — both
# are irreversible financial actions that require explicit human confirmation.
HIGH_CONSEQUENCE_ACTIONS = {"fx_lock", "usd_purchase"}
HUMAN_REVIEW_REASON = (
    "This action has irreversible financial or supplier-relationship consequences. "
    "Review carefully before applying."
)

# E6 — PII guard re-exported above (src.core.ai_safety.contains_pii_check).
# IMPORTANT: call contains_pii_check(prompt) before every Anthropic API call.

MODEL_VERSION = "rule-based-v1"


# ---------------------------------------------------------------------------
# Priority scoring helpers
# ---------------------------------------------------------------------------


def _calculate_urgency(days_until_action: int | None) -> Decimal:
    """Calculate urgency score based on time horizon."""
    if days_until_action is None or days_until_action < 7:
        return Decimal("1.0")
    if days_until_action <= 30:
        return Decimal("0.7")
    return Decimal("0.4")


def _calculate_priority_score(
    financial_impact: Decimal,
    urgency: Decimal,
    confidence: Decimal,
) -> Decimal:
    """Calculate priority score = financial_impact * urgency * confidence."""
    # Normalize confidence from 0-100 to 0-1
    conf_normalized = confidence / Decimal("100")
    score = financial_impact * urgency * conf_normalized
    return score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _assign_priority_level(
    score: Decimal,
    high_threshold: Decimal = Decimal("5000"),
    medium_threshold: Decimal = Decimal("1000"),
) -> RecommendationPriority:
    """Assign priority level based on score."""
    if score >= high_threshold:
        return RecommendationPriority.HIGH
    if score >= medium_threshold:
        return RecommendationPriority.MEDIUM
    return RecommendationPriority.LOW


# ---------------------------------------------------------------------------
# Price Recommendation Generation
# ---------------------------------------------------------------------------


async def _generate_price_recommendations(
    db: AsyncSession,
    now: datetime,
    business_id: uuid.UUID,
) -> list[AIRecommendation]:
    """Generate one price recommendation per product category with below-target products."""
    from src.pricing.service import calculate_portfolio_margin
    from src.products.models import Product, ProductCategory

    try:
        portfolio = await calculate_portfolio_margin(db, business_id=business_id)
    except Exception:
        logger.exception("price_recommendations_portfolio_failed")
        return []

    target_margin = Decimal(str(portfolio.get("target_margin", 35)))

    # Fetch category name for every active product in one query. Scoped to
    # business_id -- without it every business's product categories are
    # attributed to the caller's price recommendations (the resulting
    # AIRecommendation row is stamped with the caller's business_id
    # regardless, so its content would silently leak other tenants' data).
    cat_result = await db.execute(
        select(Product.id, ProductCategory.name)
        .join(ProductCategory, Product.category_id == ProductCategory.id)
        .where(Product.is_active.is_(True), Product.business_id == business_id)
    )
    category_by_product: dict = {pid: cat_name for pid, cat_name in cat_result.all()}

    # Build per-category buckets for below-target products
    buckets: dict[str, list[dict]] = {}
    for p in portfolio.get("products", []):
        margin_pct = Decimal(str(p.get("margin_pct", 0)))
        if margin_pct >= target_margin:
            continue

        product_id = p["product_id"]
        unit_cost = p["unit_cost"]
        selling_price = p["selling_price"]
        margin_gap = target_margin - margin_pct
        revenue_30d = p.get("revenue_30d", Decimal("0"))

        denominator = Decimal("1") - Decimal(str(target_margin)) / Decimal("100")
        if denominator <= 0:
            continue
        target_price = (unit_cost / denominator).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        cat_name = category_by_product.get(product_id, "Uncategorised")
        buckets.setdefault(cat_name, []).append(
            {
                "product_id": str(product_id),
                "product_name": p.get("product_name", ""),
                "current_price": str(selling_price),
                "suggested_price": str(target_price),
                "margin_pct": float(margin_pct),  # financial-float-ok
                "margin_gap": float(margin_gap),  # financial-float-ok
                "revenue_30d": str(revenue_30d),
            }
        )

    recommendations: list[AIRecommendation] = []
    confidence = Decimal("75.00")

    for cat_name, products in buckets.items():
        count = len(products)
        avg_gap = float(  # financial-float-ok
            (sum(Decimal(str(p["margin_gap"])) for p in products) / Decimal(str(count))).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            )
        )
        total_impact = sum(
            Decimal(p["revenue_30d"]) * Decimal(str(p["margin_gap"])) / Decimal("100")
            for p in products
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        # Sort worst-gap products first for display
        products.sort(key=lambda x: x["margin_gap"], reverse=True)

        # E1: data points = number of products with 30d revenue data
        data_points = sum(1 for p in products if Decimal(p["revenue_30d"]) > 0)
        score = _calculate_priority_score(total_impact, Decimal("1.0"), confidence)

        # E7: reason_summary and evidence
        reason_summary = (
            f"{count} product{'s' if count != 1 else ''} in {cat_name} "
            f"{'are' if count != 1 else 'is'} below the {target_margin:.0f}% margin target "
            f"by an average of {avg_gap}%. Raising prices toward target would improve portfolio margin."
        )
        evidence = [
            f"Products below target in {cat_name}: {count}",
            f"Average margin gap: {avg_gap}%",
            f"Estimated 30-day revenue impact: {total_impact} NGN",
            f"Data points used: {data_points} products with recent sales",
        ]

        rec = AIRecommendation(
            category=RecommendationCategory.PRICING,
            title=f"Review pricing for {cat_name} — {count} product{'s' if count != 1 else ''} below target",
            description=(
                f"{count} product{'s' if count != 1 else ''} in {cat_name} "
                f"{'are' if count != 1 else 'is'} below the {target_margin:.0f}% margin target. "
                f"Average gap: {avg_gap}%. Review selling prices to improve portfolio margin."
            ),
            priority=_assign_priority_level(score),
            confidence=confidence,
            expected_impact={
                "metric": "margin_improvement",
                "category_name": cat_name,
                "product_count": count,
                "avg_margin_gap": avg_gap,
                "estimated_revenue_impact": str(total_impact),
                # E1 fields stored in JSON for schema extraction
                "data_points_used": data_points,
                # E7 fields stored in JSON for schema extraction
                "reason_summary": reason_summary,
                "evidence": evidence,
            },
            action_type=ActionType.PRICE_CHANGE,
            action_payload={
                "category_name": cat_name,
                "count": count,
                "avg_gap": avg_gap,
                "products": products,
            },
            reference_type="product_category",
            status=RecommendationStatus.PENDING,
            created_at=now,
            expires_at=now + timedelta(days=RECOMMENDATION_EXPIRY_DAYS),
        )
        recommendations.append(rec)

        # E8 — Bias audit log
        await logger.ainfo(
            "recommendation_generated",
            category=cat_name,
            action=ActionType.PRICE_CHANGE.value,
            score=str(score),
            data_points_used=data_points,
            model_version=MODEL_VERSION,
        )

    return recommendations


# ---------------------------------------------------------------------------
# Order Timing Recommendations
# ---------------------------------------------------------------------------


async def _generate_order_timing_recommendations(
    db: AsyncSession,
    now: datetime,
    business_id: uuid.UUID,
) -> list[AIRecommendation]:
    """Generate reorder recommendations based on inventory depletion and FX forecasts."""
    # Reuses the shared aggregation helper (see its docstring) instead of
    # hand-rolling the same sum-across-every-row-per-product query here —
    # this function and generate_reorder_suggestions() need the identical
    # rule, and a second inline copy risks drifting from the shared one.
    #
    # Joined to Product and filtered by business_id — without it this
    # scans every business's InventoryLevel rows and generate_all_
    # recommendations() unconditionally stamps whatever comes back with
    # the caller's business_id, leaking other tenants' stock levels and
    # product names into the caller's recommendations (same class of bug
    # fixed in the sibling generate_reorder_suggestions()).
    inventory_subq = inventory_on_hand_by_product_subquery()
    result = await db.execute(
        select(
            inventory_subq.c.product_id,
            inventory_subq.c.quantity_on_hand,
            inventory_subq.c.low_stock_threshold,
        )
        .join(Product, Product.id == inventory_subq.c.product_id)
        .where(
            Product.business_id == business_id,
            inventory_subq.c.quantity_on_hand <= inventory_subq.c.low_stock_threshold,
        )
    )
    low_stock_items = list(result.all())

    if not low_stock_items:
        return []

    recommendations: list[AIRecommendation] = []

    for product_id, quantity_on_hand, low_stock_threshold in low_stock_items:
        # Calculate avg daily depletion
        depletion_result = await db.execute(
            select(
                func.coalesce(func.sum(func.abs(StockMovement.quantity_change)), 0)
            ).where(
                StockMovement.product_id == product_id,
                StockMovement.movement_type == MovementType.SALE_DEPLETION,
            )
        )
        total_depleted = depletion_result.scalar() or 0
        avg_daily = total_depleted / 30.0 if total_depleted > 0 else 0

        if avg_daily <= 0:
            continue

        days_until_stockout = int(quantity_on_hand / avg_daily)

        # Calculate optimal order quantity (demand * lead_time * 1.2 buffer)
        optimal_qty = int(avg_daily * DEFAULT_LEAD_TIME_DAYS * 1.2)

        # Estimate cost
        product_result = await db.execute(
            select(Product).where(Product.id == product_id)
        )
        product = product_result.scalar_one_or_none()
        if product is None:
            continue

        estimated_cost = product.unit_cost * optimal_qty
        financial_impact = estimated_cost  # Potential loss from stockout

        urgency = _calculate_urgency(days_until_stockout)
        confidence = Decimal("70.00")
        score = _calculate_priority_score(financial_impact, urgency, confidence)

        if days_until_stockout < 14:
            priority = RecommendationPriority.HIGH
        elif days_until_stockout < 30:
            priority = RecommendationPriority.MEDIUM
        else:
            priority = _assign_priority_level(score)

        # E1: data points = 30 days of depletion data used
        data_points = min(int(total_depleted), 30)  # capped at 30 (1 month of data)

        # E7: reason_summary and evidence
        order_reason_summary = (
            f"{product.name} is projected to stock out in {days_until_stockout} days "
            f"at current sales velocity. Immediate reorder of {optimal_qty} units recommended."
        )
        order_evidence = [
            f"Current stock: {quantity_on_hand} units",
            f"Low-stock threshold: {low_stock_threshold} units",
            f"Average daily depletion: {avg_daily:.1f} units/day",
            f"Estimated days to stockout: {days_until_stockout}",
            f"Suggested order quantity: {optimal_qty} units",
        ]

        rec = AIRecommendation(
            category=RecommendationCategory.ORDERS,
            title=f"Reorder {product.name} - {days_until_stockout} days to stockout",
            description=(
                f"Stock at {quantity_on_hand} units (threshold: {low_stock_threshold}). "
                f"Estimated stockout in {days_until_stockout} days at current velocity. "
                f"Suggested order: {optimal_qty} units."
            ),
            priority=priority,
            confidence=confidence,
            expected_impact={
                "metric": "stockout_prevention",
                "days_until_stockout": days_until_stockout,
                "estimated_cost": str(estimated_cost),
                "data_points_used": data_points,
                "reason_summary": order_reason_summary,
                "evidence": order_evidence,
            },
            action_type=ActionType.REORDER,
            action_payload={
                "product_id": str(product_id),
                "product_name": product.name,
                "suggested_quantity": optimal_qty,
                "lead_time_days": DEFAULT_LEAD_TIME_DAYS,
                "estimated_cost_ngn": str(estimated_cost),
            },
            reference_id=product_id,
            reference_type="product",
            status=RecommendationStatus.PENDING,
            created_at=now,
            expires_at=now + timedelta(days=RECOMMENDATION_EXPIRY_DAYS),
        )
        recommendations.append(rec)

        # E8 — Bias audit log
        await logger.ainfo(
            "recommendation_generated",
            category="orders",
            action=ActionType.REORDER.value,
            score=str(score),
            data_points_used=data_points,
            model_version=MODEL_VERSION,
        )

    return recommendations


# ---------------------------------------------------------------------------
# USD Hedging Recommendations
# ---------------------------------------------------------------------------


async def _generate_usd_hedge_recommendations(
    db: AsyncSession,
    now: datetime,
    business_id: uuid.UUID,
) -> list[AIRecommendation]:
    """Generate USD accumulation recommendations for upcoming FX obligations."""
    today = now.date()
    cutoff = today + timedelta(days=180)

    # Find orders with upcoming USD payments. Scoped to business_id --
    # without it every business's purchase orders are pulled into the
    # caller's USD-accumulation recommendations (same cross-tenant leak
    # class as the sibling generators in this module).
    result = await db.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.business_id == business_id,
            PurchaseOrder.status.in_(
                [
                    OrderStatus.PENDING,
                    OrderStatus.IN_PRODUCTION,
                    OrderStatus.SHIPPING,
                ]
            ),
            PurchaseOrder.currency == "USD",
            PurchaseOrder.expected_delivery_date <= cutoff,
            PurchaseOrder.expected_delivery_date >= today,
        )
    )
    orders = list(result.scalars().all())

    if not orders:
        return []

    fx_rate = await _get_latest_fx_rate(db)
    recommendations: list[AIRecommendation] = []

    for order in orders:
        # Calculate remaining balance
        paid_result = await db.execute(
            select(func.sum(OrderPayment.amount)).where(
                OrderPayment.order_id == order.id,
                OrderPayment.status == PaymentStatus.COMPLETED,
            )
        )
        paid = paid_result.scalar() or Decimal("0")
        balance_usd = order.total_amount - paid

        if balance_usd <= 0:
            continue

        usd_needed = balance_usd * Decimal("0.70")
        days_until = (
            (order.expected_delivery_date - today).days
            if order.expected_delivery_date
            else 90
        )
        weeks = max(1, days_until // 7)
        weekly_amount = (usd_needed / weeks).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        ngn_exposure = usd_needed * fx_rate

        urgency = _calculate_urgency(days_until)
        confidence = Decimal("65.00")
        financial_impact = ngn_exposure
        score = _calculate_priority_score(financial_impact, urgency, confidence)

        # E1: data points based on order history (use 1 per order as minimum)
        fx_data_points = 1

        # E7: reason_summary and evidence
        fx_reason_summary = (
            f"Order {order.order_number} requires ${usd_needed:,.2f} USD "
            f"in {days_until} days. Accumulate ${weekly_amount:,.2f}/week to reduce FX risk."
        )
        fx_evidence = [
            f"Order balance outstanding: ${balance_usd:,.2f} USD",
            f"Recommended accumulation (70%): ${usd_needed:,.2f} USD",
            f"Days until delivery: {days_until}",
            f"NGN exposure at current rate ({fx_rate}): {ngn_exposure:,.0f} NGN",
            f"Weekly target: ${weekly_amount:,.2f} USD over {weeks} weeks",
        ]

        rec = AIRecommendation(
            category=RecommendationCategory.FX,
            title=f"USD accumulation for order {order.order_number}",
            description=(
                f"Accumulate ${usd_needed:,.2f} USD over {weeks} weeks "
                f"(${weekly_amount:,.2f}/week) for order arriving in {days_until} days. "
                f"NGN exposure: {ngn_exposure:,.0f} at current rate {fx_rate}."
            ),
            priority=_assign_priority_level(score),
            confidence=confidence,
            expected_impact={
                "metric": "fx_hedge",
                "usd_needed": str(usd_needed),
                "ngn_exposure": str(ngn_exposure),
                "weeks": weeks,
                "weekly_usd": str(weekly_amount),
                "data_points_used": fx_data_points,
                "reason_summary": fx_reason_summary,
                "evidence": fx_evidence,
            },
            action_type=ActionType.USD_PURCHASE,
            action_payload={
                "order_id": str(order.id),
                "order_number": order.order_number,
                "usd_needed": str(usd_needed),
                "weekly_amount": str(weekly_amount),
                "weeks": weeks,
            },
            reference_id=order.id,
            reference_type="purchase_order",
            status=RecommendationStatus.PENDING,
            created_at=now,
            expires_at=now + timedelta(days=RECOMMENDATION_EXPIRY_DAYS),
        )
        recommendations.append(rec)

        # E8 — Bias audit log
        await logger.ainfo(
            "recommendation_generated",
            category="fx",
            action=ActionType.USD_PURCHASE.value,
            score=str(score),
            data_points_used=fx_data_points,
            model_version=MODEL_VERSION,
        )

    return recommendations


# ---------------------------------------------------------------------------
# Liquidity Recommendations
# ---------------------------------------------------------------------------


async def _generate_liquidity_recommendations(
    db: AsyncSession,
    now: datetime,
    business_id: uuid.UUID,
) -> list[AIRecommendation]:
    """Generate liquidity and DSCR-based corrective action recommendations."""
    from src.cashflow.service import (
        _calculate_monthly_loan_payment,
        _calculate_monthly_operating_costs,
        _calculate_monthly_revenue,
    )

    try:
        monthly_revenue = await _calculate_monthly_revenue(db, business_id)
        monthly_opex = await _calculate_monthly_operating_costs(db, business_id)
        monthly_loan = await _calculate_monthly_loan_payment(db, business_id)
    except Exception:
        logger.exception(
            "liquidity_recommendations_failed",
            business_id=str(business_id),
        )
        return []

    noi = monthly_revenue - monthly_opex
    dscr = (
        (noi / monthly_loan).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        if monthly_loan > 0
        else Decimal("999.000")
    )

    # Estimate simple runway
    monthly_burn = monthly_opex + monthly_loan - monthly_revenue
    if monthly_burn > 0 and monthly_revenue > 0:
        runway_months = int(monthly_revenue * 3 / monthly_burn)  # ~3 months cash
    else:
        runway_months = 999

    recommendations: list[AIRecommendation] = []

    if dscr >= Decimal("1.5") and runway_months >= 4:
        return recommendations

    # Determine priority
    if dscr < Decimal("1.0"):
        priority = RecommendationPriority.HIGH
    else:
        priority = RecommendationPriority.MEDIUM

    actions = []

    # Suggest delaying non-critical orders
    far_orders_result = await db.execute(
        select(func.count(PurchaseOrder.id)).where(
            PurchaseOrder.status == OrderStatus.PENDING,
            PurchaseOrder.expected_delivery_date > now.date() + timedelta(days=90),
        )
    )
    far_orders_count = far_orders_result.scalar() or 0
    if far_orders_count > 0:
        actions.append(
            f"Consider delaying {far_orders_count} non-critical orders (delivery >90 days)"
        )

    # Suggest loan deferral
    loan_result = await db.execute(
        select(func.count(LoanObligation.id)).where(
            LoanObligation.status == LoanStatus.ACTIVE
        )
    )
    active_loans = loan_result.scalar() or 0
    if active_loans > 0 and dscr < Decimal("1.2"):
        actions.append(
            f"Negotiate payment deferral on {active_loans} active loan(s) to improve DSCR"
        )

    # Suggest cost reduction
    if monthly_opex > monthly_revenue * Decimal("0.7"):
        actions.append(
            f"Operating costs ({monthly_opex:,.0f}) exceed 70% of revenue. Review for reductions."
        )

    if not actions:
        actions.append("Review pricing strategy to increase revenue margins")

    confidence = Decimal("80.00")
    # E1: 3 months of financial data (revenue + opex + loan) = 3 data sources
    liq_data_points = 3

    # E7: reason_summary and evidence
    liq_reason_summary = (
        f"DSCR of {dscr} is below the 1.5 target (CBN prudential guidelines 2021). "
        f"With ~{runway_months} months runway, corrective action is recommended."
    )
    liq_evidence = [
        f"Current DSCR: {dscr} (target: ≥1.5)",
        f"Monthly revenue: {monthly_revenue:,.0f} NGN",
        f"Monthly operating costs: {monthly_opex:,.0f} NGN",
        f"Monthly loan payment: {monthly_loan:,.0f} NGN",
        f"Estimated cash runway: {runway_months} months",
    ]

    rec = AIRecommendation(
        category=RecommendationCategory.CASHFLOW,
        title=f"Liquidity alert: DSCR {dscr} | Runway ~{runway_months}mo",
        description=(
            f"Current DSCR is {dscr} (target: 1.5+). "
            f"Estimated cash runway: {runway_months} months. "
            f"Corrective actions: {'; '.join(actions)}"
        ),
        priority=priority,
        confidence=confidence,
        expected_impact={
            "metric": "liquidity_improvement",
            "current_dscr": str(dscr),
            "monthly_burn": str(monthly_burn),
            "actions": actions,
            "data_points_used": liq_data_points,
            "reason_summary": liq_reason_summary,
            "evidence": liq_evidence,
        },
        action_type=ActionType.COST_CUT,
        action_payload={
            "dscr": str(dscr),
            "runway_months": runway_months,
            "actions": actions,
        },
        reference_type="cashflow",
        status=RecommendationStatus.PENDING,
        created_at=now,
        expires_at=now + timedelta(days=14),  # Shorter expiry for urgency
    )
    recommendations.append(rec)

    # E8 — Bias audit log
    await logger.ainfo(
        "recommendation_generated",
        category="cashflow",
        action=ActionType.COST_CUT.value,
        score=str(_calculate_priority_score(abs(monthly_burn), Decimal("1.0"), confidence)),
        data_points_used=liq_data_points,
        model_version=MODEL_VERSION,
    )

    return recommendations


# ---------------------------------------------------------------------------
# Unified Recommendation Generation
# ---------------------------------------------------------------------------


async def generate_all_recommendations(
    db: AsyncSession,
    user_id: uuid.UUID,
    business_id: uuid.UUID,
) -> list[AIRecommendation]:
    """Orchestrate all recommendation generators and store results."""
    now = datetime.now(timezone.utc)

    # Expire old pending recommendations for this business
    old_result = await db.execute(
        select(AIRecommendation).where(
            AIRecommendation.business_id == business_id,
            AIRecommendation.status == RecommendationStatus.PENDING,
            AIRecommendation.expires_at < now,
        )
    )
    for rec in old_result.scalars().all():
        rec.status = RecommendationStatus.EXPIRED

    # Generate from all sources
    all_recs: list[AIRecommendation] = []

    price_recs = await _generate_price_recommendations(db, now, business_id)
    all_recs.extend(price_recs)

    order_recs = await _generate_order_timing_recommendations(db, now, business_id)
    all_recs.extend(order_recs)

    usd_recs = await _generate_usd_hedge_recommendations(db, now, business_id)
    all_recs.extend(usd_recs)

    liquidity_recs = await _generate_liquidity_recommendations(db, now, business_id)
    all_recs.extend(liquidity_recs)

    # Stamp every new recommendation with the business_id before storing
    for rec in all_recs:
        rec.business_id = business_id
        db.add(rec)

    await db.flush()

    await logger.ainfo(
        "ai_recommendations_generated",
        total=len(all_recs),
        pricing=len(price_recs),
        orders=len(order_recs),
        usd_hedge=len(usd_recs),
        liquidity=len(liquidity_recs),
    )

    # Sort by priority score heuristic: HIGH=3, MEDIUM=2, LOW=1
    priority_order = {
        RecommendationPriority.HIGH: 3,
        RecommendationPriority.MEDIUM: 2,
        RecommendationPriority.LOW: 1,
    }
    all_recs.sort(key=lambda r: priority_order.get(r.priority, 0), reverse=True)

    return all_recs


# ---------------------------------------------------------------------------
# Recommendation CRUD
# ---------------------------------------------------------------------------


async def get_recommendations(
    db: AsyncSession,
    category: str | None = None,
    status_filter: str | None = None,
    limit: int = 50,
    business_id: uuid.UUID | None = None,
) -> list[AIRecommendation]:
    """Get recommendations with optional filters."""
    query = select(AIRecommendation)

    if business_id is not None:
        query = query.where(AIRecommendation.business_id == business_id)

    if status_filter:
        query = query.where(AIRecommendation.status == status_filter)
    else:
        query = query.where(AIRecommendation.status == RecommendationStatus.PENDING)

    if category:
        query = query.where(AIRecommendation.category == category)

    query = query.order_by(AIRecommendation.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_recommendation(
    db: AsyncSession,
    recommendation_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> AIRecommendation:
    """Get a single recommendation by ID, scoped to business if provided."""
    query = select(AIRecommendation).where(AIRecommendation.id == recommendation_id)
    if business_id is not None:
        query = query.where(AIRecommendation.business_id == business_id)
    result = await db.execute(query)
    rec = result.scalar_one_or_none()
    if rec is None:
        raise RecommendationNotFoundError(recommendation_id)
    return rec


async def apply_recommendation(
    db: AsyncSession,
    recommendation_id: uuid.UUID,
    user_id: uuid.UUID,
    notes: str | None = None,
    business_id: uuid.UUID | None = None,
    confirmed: bool = False,
) -> AIRecommendation:
    """Apply a recommendation: update status and route to domain service.

    E4: High-consequence actions (see HIGH_CONSEQUENCE_ACTIONS) require confirmed=True.
    """
    rec = await get_recommendation(db, recommendation_id, business_id=business_id)

    if rec.status != RecommendationStatus.PENDING:
        raise RecommendationAlreadyProcessedError(recommendation_id, rec.status)

    now = datetime.now(timezone.utc)
    if rec.expires_at < now:
        rec.status = RecommendationStatus.EXPIRED
        await db.flush()
        raise RecommendationExpiredError(recommendation_id, rec.expires_at)

    # E4 — Human review gate for high-consequence actions
    action_str = (
        rec.action_type.value
        if hasattr(rec.action_type, "value")
        else str(rec.action_type)
    )
    if action_str in HIGH_CONSEQUENCE_ACTIONS and not confirmed:
        from fastapi import HTTPException, status as http_status
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "This action requires explicit confirmation. "
                "Resubmit with confirmed=true."
            ),
        )

    # Route based on action type
    if rec.action_type == ActionType.PRICE_CHANGE and rec.action_payload:
        payload = rec.action_payload
        if "product_id" in payload and "suggested_price" in payload:
            # Legacy single-product payload: apply the suggested price directly.
            product_id = uuid.UUID(payload["product_id"])
            new_price = Decimal(payload["suggested_price"])
            product_result = await db.execute(
                select(Product).where(Product.id == product_id)
            )
            product = product_result.scalar_one_or_none()
            if product:
                product.selling_price = new_price
        # Grouped category payload ({category_name, products:[...]}):
        # status update below marks it reviewed; user applies via the optimizer.

    # For other types (REORDER, USD_PURCHASE, COST_CUT), flag for manual action
    # The status update itself marks it as actioned

    rec.status = RecommendationStatus.APPLIED
    rec.accepted_by = user_id
    rec.accepted_at = now

    await db.flush()

    await logger.ainfo(
        "recommendation_applied",
        recommendation_id=str(recommendation_id),
        action_type=rec.action_type,
        category=rec.category,
    )
    return rec


async def dismiss_recommendation(
    db: AsyncSession,
    recommendation_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str,
    business_id: uuid.UUID | None = None,
) -> AIRecommendation:
    """Dismiss a recommendation with a reason."""
    rec = await get_recommendation(db, recommendation_id, business_id=business_id)

    if rec.status != RecommendationStatus.PENDING:
        raise RecommendationAlreadyProcessedError(recommendation_id, rec.status)

    now = datetime.now(timezone.utc)
    rec.status = RecommendationStatus.DISMISSED
    rec.dismissed_reason = reason
    rec.accepted_by = user_id  # reuse field for tracking who dismissed
    rec.accepted_at = now

    await db.flush()

    await logger.ainfo(
        "recommendation_dismissed",
        recommendation_id=str(recommendation_id),
        reason=reason,
    )
    return rec


async def get_impact_summary(
    db: AsyncSession,
    business_id: uuid.UUID | None = None,
) -> dict:
    """Aggregate expected impact from pending recommendations."""
    query = select(AIRecommendation).where(
        AIRecommendation.status == RecommendationStatus.PENDING
    )
    if business_id is not None:
        query = query.where(AIRecommendation.business_id == business_id)
    result = await db.execute(query)
    recs = list(result.scalars().all())

    total_revenue_impact = Decimal("0")
    total_cost_savings = Decimal("0")
    by_category: dict[str, dict] = {}

    for rec in recs:
        cat = rec.category
        if cat not in by_category:
            by_category[cat] = {
                "category": cat,
                "count": 0,
                "projected_impact": Decimal("0"),
            }
        by_category[cat]["count"] += 1

        if rec.expected_impact:
            impact_val = Decimal(
                rec.expected_impact.get("estimated_revenue_impact", "0")
            )
            if rec.category == RecommendationCategory.PRICING:
                total_revenue_impact += impact_val
            elif rec.category == RecommendationCategory.CASHFLOW:
                total_cost_savings += abs(
                    Decimal(rec.expected_impact.get("monthly_burn", "0"))
                )
            by_category[cat]["projected_impact"] += impact_val

    return {
        "total_pending": len(recs),
        "projected_revenue_impact": total_revenue_impact,
        "projected_cost_savings": total_cost_savings,
        "by_category": [
            {
                "category": v["category"],
                "count": v["count"],
                "projected_impact": str(v["projected_impact"]),
            }
            for v in by_category.values()
        ],
    }


async def get_recommendation_history(
    db: AsyncSession,
    limit: int = 50,
    business_id: uuid.UUID | None = None,
) -> list[AIRecommendation]:
    """Get applied/dismissed recommendation history."""
    query = (
        select(AIRecommendation)
        .where(
            AIRecommendation.status.in_(
                [
                    RecommendationStatus.APPLIED,
                    RecommendationStatus.DISMISSED,
                ]
            )
        )
    )
    if business_id is not None:
        query = query.where(AIRecommendation.business_id == business_id)
    query = query.order_by(AIRecommendation.accepted_at.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# USD Accumulation Schedule
# ---------------------------------------------------------------------------


async def _get_latest_fx_rate(db: AsyncSession) -> Decimal:
    """Try to get the latest USDNGN rate from the database."""
    try:
        from src.fx.models import FXRate

        fx_result = await db.execute(
            select(FXRate.rate)
            .where(FXRate.pair == "USDNGN")
            .order_by(FXRate.timestamp.desc())
            .limit(1)
        )
        latest = fx_result.scalar()
        if latest:
            return latest
    except Exception:
        logger.exception("get_latest_fx_rate_failed")
    return DEFAULT_FX_RATE


async def generate_usd_accumulation_schedule(
    db: AsyncSession,
    order_id: uuid.UUID,
) -> dict:
    """Generate a weekly USD accumulation schedule for an order."""
    result = await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == order_id))
    order = result.scalar_one_or_none()
    if order is None:
        from src.orders.exceptions import OrderNotFoundError

        raise OrderNotFoundError(order_id)

    today = date.today()

    # Calculate remaining balance
    paid_result = await db.execute(
        select(func.sum(OrderPayment.amount)).where(
            OrderPayment.order_id == order_id,
            OrderPayment.status == PaymentStatus.COMPLETED,
        )
    )
    paid = paid_result.scalar() or Decimal("0")
    balance_usd = order.total_amount - paid

    usd_needed = balance_usd * Decimal("0.70")
    delivery_date = order.expected_delivery_date or (today + timedelta(days=90))
    days_until_arrival = max(1, (delivery_date - today).days)
    weeks = max(1, days_until_arrival // 7)
    weekly_amount = (usd_needed / weeks).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    fx_rate = await _get_latest_fx_rate(db)

    schedule = []
    for week in range(weeks):
        purchase_date = today + timedelta(days=week * 7)
        # Try to get FX forecast for this date
        forecasted_rate = fx_rate
        try:
            from src.fx.forecast_service import get_forecast_for_date

            forecast = await get_forecast_for_date(db, "USDNGN", purchase_date)
            forecasted_rate = forecast.base_rate
        except Exception:
            pass

        ngn_amount = (weekly_amount * forecasted_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        schedule.append(
            {
                "week": week + 1,
                "purchase_date": purchase_date.isoformat(),
                "usd_amount": str(weekly_amount),
                "forecasted_fx_rate": str(forecasted_rate),
                "ngn_amount": str(ngn_amount),
            }
        )

    return {
        "order_id": str(order_id),
        "total_usd_needed": str(usd_needed),
        "weeks": weeks,
        "weekly_amount": str(weekly_amount),
        "schedule": schedule,
    }


# ---------------------------------------------------------------------------
# USD Strategy Config
# ---------------------------------------------------------------------------


async def get_usd_strategy_config(
    db: AsyncSession,
) -> USDStrategyConfig:
    """Get the current USD strategy configuration."""
    result = await db.execute(
        select(USDStrategyConfig).order_by(USDStrategyConfig.updated_at.desc()).limit(1)
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise USDStrategyConfigNotFoundError()
    return config


async def update_usd_strategy_config(
    db: AsyncSession,
    data,
    user_id: uuid.UUID,
) -> USDStrategyConfig:
    """Create or update USD strategy configuration."""
    now = datetime.now(timezone.utc)

    try:
        config = await get_usd_strategy_config(db)
        config.target_usd_balance = data.target_usd_balance
        config.risk_tolerance = RiskTolerance(data.risk_tolerance)
        config.max_single_purchase_pct = data.max_single_purchase_pct
        config.preferred_rate_percentile = data.preferred_rate_percentile
        config.lookback_days = data.lookback_days
        config.updated_by = user_id
        config.updated_at = now
    except USDStrategyConfigNotFoundError:
        config = USDStrategyConfig(
            target_usd_balance=data.target_usd_balance,
            current_usd_balance=Decimal("0"),
            risk_tolerance=RiskTolerance(data.risk_tolerance),
            max_single_purchase_pct=data.max_single_purchase_pct,
            preferred_rate_percentile=data.preferred_rate_percentile,
            lookback_days=data.lookback_days,
            updated_by=user_id,
            updated_at=now,
        )
        db.add(config)

    await db.flush()
    return config


# ---------------------------------------------------------------------------
# Reorder Suggestions
# ---------------------------------------------------------------------------


async def generate_reorder_suggestions(
    db: AsyncSession,
    business_id: uuid.UUID,
) -> list[ReorderSuggestion]:
    """Generate reorder suggestions for products at or below reorder point."""
    # A product can have more than one InventoryLevel row (the aggregate
    # row plus one per variant, see data_import/recompute.py) — joining
    # directly would duplicate a product with multiple rows into multiple
    # suggestions, while scoping to variant_id IS NULL only would silently
    # skip a product that has no aggregate row at all (e.g. one imported
    # with only variant-level sales). Sum on-hand across every row per
    # product instead, so exactly one suggestion is produced per product
    # using its true total stock.
    #
    # Product.business_id filter is required, not optional — this function
    # is now called automatically after every import/rollback (see
    # data_import/recompute.py's regenerate_reorder_suggestions_for_business()),
    # so without it every call would generate suggestions for every
    # business's products, not just the caller's, and stamp them with the
    # caller's business_id — a cross-tenant data leak on every import.
    inventory_subq = inventory_on_hand_by_product_subquery()
    result = await db.execute(
        select(inventory_subq.c.quantity_on_hand, Product)
        .join(Product, Product.id == inventory_subq.c.product_id)
        .where(Product.is_active.is_(True), Product.business_id == business_id)
    )
    rows = result.all()

    now = datetime.now(timezone.utc)
    today = now.date()
    suggestions: list[ReorderSuggestion] = []

    for quantity_on_hand, product in rows:
        # Calculate average daily demand from last 90 days
        ninety_days_ago = today - timedelta(days=90)
        sales_result = await db.execute(
            select(
                func.sum(Sale.quantity),
                func.count(func.distinct(Sale.sale_date)),
            ).where(
                Sale.product_id == product.id,
                Sale.status == SaleStatus.COMPLETED,
                Sale.sale_date >= ninety_days_ago,
            )
        )
        total_sold, data_points_used = sales_result.one()
        total_sold = total_sold or 0
        data_points_used = data_points_used or 0

        if total_sold <= 0:
            continue

        avg_daily_demand = Decimal(str(total_sold)) / Decimal("90")
        demand_variability = avg_daily_demand * Decimal("0.2")  # Simple estimate

        # Calculate reorder point and safety stock
        safety_stock = int(
            float(SAFETY_STOCK_MULTIPLIER)  # financial-float-ok
            * float(demand_variability)  # financial-float-ok
            * (DEFAULT_LEAD_TIME_DAYS**0.5)
        )
        reorder_point = int(
            float(avg_daily_demand) * DEFAULT_LEAD_TIME_DAYS + safety_stock  # financial-float-ok
        )

        if quantity_on_hand > reorder_point:
            continue

        # Economic Order Quantity (Wilson formula simplified)
        annual_demand = float(avg_daily_demand) * 365  # financial-float-ok
        ordering_cost = 50000  # Fixed ordering cost NGN
        holding_cost = float(product.unit_cost) * 0.20  # 20% of unit cost  # financial-float-ok
        eoq = (
            int((2 * annual_demand * ordering_cost / holding_cost) ** 0.5)
            if holding_cost > 0
            else 100
        )
        suggested_qty = max(
            eoq, int(float(avg_daily_demand) * DEFAULT_LEAD_TIME_DAYS * 1.2)  # financial-float-ok
        )

        # Estimate stockout date
        if float(avg_daily_demand) > 0:  # financial-float-ok
            days_left = int(quantity_on_hand / float(avg_daily_demand))  # financial-float-ok
            stockout_date = today + timedelta(days=days_left)
        else:
            days_left = 999
            stockout_date = None

        confidence = Decimal("75.00")
        reasoning = (
            f"Current stock ({quantity_on_hand}) at or below reorder point ({reorder_point}). "
            f"Avg daily demand: {float(avg_daily_demand):.1f} units. "  # financial-float-ok
            f"Safety stock: {safety_stock}. Lead time: {DEFAULT_LEAD_TIME_DAYS} days. "
            f"EOQ: {eoq}. Suggested order: {suggested_qty} units."
        )

        suggestion = ReorderSuggestion(
            business_id=business_id,
            product_id=product.id,
            current_stock=quantity_on_hand,
            reorder_point=reorder_point,
            suggested_order_quantity=suggested_qty,
            economic_order_quantity=eoq,
            safety_stock=safety_stock,
            lead_time_days=DEFAULT_LEAD_TIME_DAYS,
            avg_daily_demand=avg_daily_demand.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            demand_variability=demand_variability.quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            ),
            estimated_stockout_date=stockout_date,
            confidence=confidence,
            # E1 — how many distinct sale-days fed this forecast, so the
            # frontend/API consumer can judge whether the demand estimate is
            # backed by sparse or solid history rather than trusting a bare
            # confidence score.
            data_points_used=data_points_used,
            reasoning=reasoning,
            status=ReorderStatus.PENDING,
            created_at=now,
        )
        db.add(suggestion)
        suggestions.append(suggestion)

    await db.flush()

    await logger.ainfo("reorder_suggestions_generated", count=len(suggestions))
    return suggestions


async def get_reorder_suggestions(
    db: AsyncSession,
    business_id: uuid.UUID | None = None,
) -> list[ReorderSuggestion]:
    """Get all pending reorder suggestions."""
    query = (
        select(ReorderSuggestion)
        .where(ReorderSuggestion.status == ReorderStatus.PENDING)
    )
    if business_id is not None:
        query = query.where(ReorderSuggestion.business_id == business_id)
    query = query.order_by(ReorderSuggestion.estimated_stockout_date.asc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_reorder_suggestion(
    db: AsyncSession,
    product_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> ReorderSuggestion:
    """Get reorder suggestion for a specific product."""
    query = (
        select(ReorderSuggestion)
        .where(
            ReorderSuggestion.product_id == product_id,
            ReorderSuggestion.status == ReorderStatus.PENDING,
        )
    )
    if business_id is not None:
        query = query.where(ReorderSuggestion.business_id == business_id)
    query = query.order_by(ReorderSuggestion.created_at.desc()).limit(1)
    result = await db.execute(query)
    suggestion = result.scalar_one_or_none()
    if suggestion is None:
        raise ReorderSuggestionNotFoundError(product_id)
    return suggestion


async def approve_reorder(
    db: AsyncSession,
    product_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> ReorderSuggestion:
    """Approve a reorder suggestion (mark as approved for manual order creation)."""
    suggestion = await get_reorder_suggestion(db, product_id, business_id=business_id)
    suggestion.status = ReorderStatus.APPROVED
    await db.flush()

    await logger.ainfo(
        "reorder_suggestion_approved",
        product_id=str(product_id),
        quantity=suggestion.suggested_order_quantity,
    )
    return suggestion


# ---------------------------------------------------------------------------
# Reorder Config
# ---------------------------------------------------------------------------


async def get_reorder_config(
    db: AsyncSession,
    business_id: uuid.UUID | None = None,
) -> ReorderConfig:
    """Get reorder configuration, scoped to business if provided."""
    query = select(ReorderConfig)
    if business_id is not None:
        query = query.where(ReorderConfig.business_id == business_id)
    query = query.order_by(ReorderConfig.updated_at.desc()).limit(1)
    result = await db.execute(query)
    config = result.scalar_one_or_none()
    if config is None:
        # Return defaults (business_id may be None for backward compat)
        return ReorderConfig(
            business_id=business_id or uuid.UUID("00000000-0000-0000-0000-000000000000"),
            default_lead_time_days=DEFAULT_LEAD_TIME_DAYS,
            safety_stock_multiplier=SAFETY_STOCK_MULTIPLIER,
            service_level_target=Decimal("95.00"),
            demand_lookback_days=90,
            holding_cost_pct=Decimal("20.00"),
            updated_by=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            updated_at=datetime.now(timezone.utc),
        )
    return config
