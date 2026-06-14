"""Cashflow domain service: projections, DSCR, runway, stress scenarios."""

import enum
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cashflow.exceptions import LoanNotFoundError, ProjectionNotFoundError
from src.cashflow.models import (
    CashflowProjection,
    CostFrequency,
    LoanObligation,
    LoanPaymentSchedule,
    LoanStatus,
    OperatingCost,
    StressScenario,
    TriageRecord,
    TriageStatus,
)
from src.fx.service import get_latest_rate_value, get_previous_rate_value
from src.orders.models import OrderPayment, OrderStatus, PaymentStatus, PurchaseOrder
from src.sales.models import Sale, SaleStatus

logger = structlog.get_logger()

# Frequency multipliers to normalize to monthly
FREQUENCY_TO_MONTHLY: dict[str, Decimal] = {
    CostFrequency.DAILY: Decimal("30"),
    CostFrequency.WEEKLY: Decimal("4.33"),
    CostFrequency.MONTHLY: Decimal("1"),
    CostFrequency.QUARTERLY: Decimal("1") / Decimal("3"),
    CostFrequency.ANNUALLY: Decimal("1") / Decimal("12"),
}

DEFAULT_FX_RATE = Decimal("1500.000000")


class ScenarioType(str, enum.Enum):
    BASE = "BASE"
    FX_SHOCK_10 = "FX_SHOCK_10"
    FX_SHOCK_20 = "FX_SHOCK_20"
    DEMAND_DROP_10 = "DEMAND_DROP_10"
    DEMAND_DROP_20 = "DEMAND_DROP_20"
    COMBINED_STRESS = "COMBINED_STRESS"


class RiskRating(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


def _get_scenario_params(scenario_type: str) -> dict:
    """Get revenue and FX adjustments for a scenario."""
    params = {
        "revenue_shock_pct": Decimal("0"),
        "fx_shock_pct": Decimal("0"),
    }
    if scenario_type == ScenarioType.FX_SHOCK_10:
        params["fx_shock_pct"] = Decimal("10")
    elif scenario_type == ScenarioType.FX_SHOCK_20:
        params["fx_shock_pct"] = Decimal("20")
    elif scenario_type == ScenarioType.DEMAND_DROP_10:
        params["revenue_shock_pct"] = Decimal("-10")
    elif scenario_type == ScenarioType.DEMAND_DROP_20:
        params["revenue_shock_pct"] = Decimal("-20")
    elif scenario_type == ScenarioType.COMBINED_STRESS:
        params["revenue_shock_pct"] = Decimal("-20")
        params["fx_shock_pct"] = Decimal("20")
    return params


VALID_SCENARIO_TYPES = {e.value for e in ScenarioType}


# ---------------------------------------------------------------------------
# Loan Obligations
# ---------------------------------------------------------------------------


async def create_loan(db: AsyncSession, data, user_id: uuid.UUID) -> LoanObligation:
    """Create a loan obligation."""
    end_date = data.start_date + timedelta(days=data.term_months * 30)
    loan = LoanObligation(
        lender_name=data.lender_name,
        principal_amount=data.principal_amount,
        outstanding_balance=data.principal_amount,
        interest_rate=data.interest_rate,
        term_months=data.term_months,
        start_date=data.start_date,
        end_date=end_date,
        payment_frequency=data.payment_frequency,
        monthly_payment=data.monthly_payment,
        currency=data.currency,
        status=LoanStatus.ACTIVE,
        notes=data.notes,
    )
    db.add(loan)
    await db.flush()
    return loan


async def get_loans(db: AsyncSession) -> list[LoanObligation]:
    """List active loans."""
    result = await db.execute(
        select(LoanObligation).where(LoanObligation.status == LoanStatus.ACTIVE)
    )
    return list(result.scalars().all())


async def get_loan(db: AsyncSession, loan_id: uuid.UUID) -> LoanObligation:
    """Get a specific loan."""
    result = await db.execute(
        select(LoanObligation).where(LoanObligation.id == loan_id)
    )
    loan = result.scalar_one_or_none()
    if loan is None:
        raise LoanNotFoundError(loan_id)
    return loan


# ---------------------------------------------------------------------------
# Operating Costs
# ---------------------------------------------------------------------------


def _normalize_to_monthly(amount: Decimal, frequency: str) -> Decimal:
    """Normalize cost amount to monthly equivalent."""
    multiplier = FREQUENCY_TO_MONTHLY.get(frequency, Decimal("1"))
    return (amount * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def create_operating_cost(
    db: AsyncSession, data, user_id: uuid.UUID
) -> OperatingCost:
    """Create an operating cost with frequency normalization."""
    monthly_equivalent = _normalize_to_monthly(data.cost_amount, data.frequency)
    cost = OperatingCost(
        cost_name=data.cost_name,
        cost_amount=data.cost_amount,
        frequency=data.frequency,
        monthly_equivalent=monthly_equivalent,
        category=data.category,
        is_active=True,
        created_by=user_id,
    )
    db.add(cost)
    await db.flush()
    return cost


async def get_operating_costs(db: AsyncSession) -> list[OperatingCost]:
    """List active operating costs."""
    result = await db.execute(
        select(OperatingCost).where(OperatingCost.is_active.is_(True))
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Projection building blocks
# ---------------------------------------------------------------------------


async def _calculate_monthly_revenue(
    db: AsyncSession, scenario_type: str = "BASE"
) -> Decimal:
    """Calculate baseline monthly revenue from last 90 days of sales."""
    ninety_days_ago = (datetime.now(timezone.utc) - timedelta(days=90)).date()
    result = await db.execute(
        select(func.sum(Sale.total_amount)).where(
            Sale.status == SaleStatus.COMPLETED,
            Sale.sale_date >= ninety_days_ago,
        )
    )
    total_90d = result.scalar() or Decimal("0")
    monthly_revenue = (total_90d / Decimal("3")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    params = _get_scenario_params(scenario_type)
    if params["revenue_shock_pct"] != 0:
        shock = Decimal("1") + params["revenue_shock_pct"] / Decimal("100")
        monthly_revenue = (monthly_revenue * shock).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    return monthly_revenue


async def _calculate_monthly_loan_payment(db: AsyncSession) -> Decimal:
    """Sum monthly payments for all active loans."""
    result = await db.execute(
        select(func.sum(LoanObligation.monthly_payment)).where(
            LoanObligation.status == LoanStatus.ACTIVE
        )
    )
    return result.scalar() or Decimal("0")


async def _calculate_monthly_operating_costs(db: AsyncSession) -> Decimal:
    """Sum monthly equivalent for all active operating costs."""
    result = await db.execute(
        select(func.sum(OperatingCost.monthly_equivalent)).where(
            OperatingCost.is_active.is_(True)
        )
    )
    return result.scalar() or Decimal("0")


async def _calculate_fx_obligations(
    db: AsyncSession,
    target_month_start: date,
    target_month_end: date,
    fx_rate: Decimal = DEFAULT_FX_RATE,
    scenario_type: str = "BASE",
) -> Decimal:
    """Calculate FX obligations for orders arriving in target month.

    70% of remaining order balance * FX rate.
    """
    result = await db.execute(
        select(
            PurchaseOrder.id,
            PurchaseOrder.total_amount,
        ).where(
            PurchaseOrder.status.in_(
                [
                    OrderStatus.PENDING,
                    OrderStatus.IN_PRODUCTION,
                    OrderStatus.SHIPPING,
                ]
            ),
            PurchaseOrder.expected_delivery_date >= target_month_start,
            PurchaseOrder.expected_delivery_date <= target_month_end,
            PurchaseOrder.currency == "USD",
        )
    )
    orders = result.all()

    total_fx = Decimal("0")
    for order_id, total_amount in orders:
        paid_result = await db.execute(
            select(func.sum(OrderPayment.amount)).where(
                OrderPayment.order_id == order_id,
                OrderPayment.status == PaymentStatus.COMPLETED,
            )
        )
        paid = paid_result.scalar() or Decimal("0")
        balance = total_amount - paid
        total_fx += balance * Decimal("0.70") * fx_rate

    # Apply FX shock
    params = _get_scenario_params(scenario_type)
    if params["fx_shock_pct"] != 0:
        shock = Decimal("1") + params["fx_shock_pct"] / Decimal("100")
        total_fx = total_fx * shock

    return total_fx.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def _get_latest_fx_rate(db: AsyncSession) -> Decimal:
    """Try to get the latest FX rate from the database."""
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
        pass
    return DEFAULT_FX_RATE


def _calculate_dscr(
    revenue: Decimal, operating_costs: Decimal, loan_payment: Decimal
) -> Decimal:
    """Calculate DSCR = (revenue - operating_costs) / loan_payment."""
    if loan_payment <= 0:
        return Decimal("999.000")
    noi = revenue - operating_costs
    return (noi / loan_payment).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _assign_risk_rating(dscr: Decimal, runway_months: Decimal) -> str:
    """Assign risk rating based on DSCR and runway."""
    if dscr < Decimal("1.0") or runway_months < Decimal("3"):
        return RiskRating.HIGH
    if dscr < Decimal("1.5") or runway_months < Decimal("6"):
        return RiskRating.MEDIUM
    return RiskRating.LOW


# ---------------------------------------------------------------------------
# 6-Month Cashflow Projection
# ---------------------------------------------------------------------------


async def generate_cashflow_projection(
    db: AsyncSession,
    user_id: uuid.UUID,
    months: int = 6,
    scenario_type: str = "BASE",
) -> CashflowProjection:
    """Generate a multi-month cashflow projection."""
    now = datetime.now(timezone.utc)
    today = now.date()

    monthly_revenue = await _calculate_monthly_revenue(db, scenario_type)
    monthly_loan = await _calculate_monthly_loan_payment(db)
    monthly_opex = await _calculate_monthly_operating_costs(db)
    fx_rate = await _get_latest_fx_rate(db)

    monthly_buckets = []
    cumulative = Decimal("0")
    total_inflows = Decimal("0")
    total_outflows = Decimal("0")

    for i in range(months):
        target_month = today.month + i
        target_year = today.year + (target_month - 1) // 12
        target_month = ((target_month - 1) % 12) + 1
        month_start = date(target_year, target_month, 1)
        if target_month == 12:
            month_end = date(target_year, 12, 31)
        else:
            month_end = date(target_year, target_month + 1, 1) - timedelta(days=1)

        fx_obligations = await _calculate_fx_obligations(
            db, month_start, month_end, fx_rate, scenario_type
        )

        total_expenses = monthly_loan + monthly_opex + fx_obligations
        net = monthly_revenue - total_expenses
        cumulative += net

        dscr = _calculate_dscr(monthly_revenue, monthly_opex, monthly_loan)

        if net < 0 and cumulative > 0:
            runway = (cumulative / abs(net)).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            )
        elif cumulative <= 0:
            runway = Decimal("0")
        else:
            runway = Decimal("999.0")

        risk = _assign_risk_rating(dscr, runway)

        monthly_buckets.append(
            {
                "month": month_start.isoformat()[:7],
                "projected_revenue": str(monthly_revenue),
                "projected_loan_payment": str(monthly_loan),
                "projected_operating_costs": str(monthly_opex),
                "projected_fx_obligations": str(fx_obligations),
                "net_cashflow": str(net),
                "cumulative_cashflow": str(cumulative),
                "dscr": str(dscr),
                "cash_runway_months": str(runway),
                "risk_rating": risk,
            }
        )

        total_inflows += monthly_revenue
        total_outflows += total_expenses

    net_total = total_inflows - total_outflows

    projection = CashflowProjection(
        projection_date=today,
        horizon_months=months,
        monthly_buckets=monthly_buckets,
        total_inflows=total_inflows,
        total_outflows=total_outflows,
        net_cashflow=net_total,
        assumptions={
            "scenario_type": scenario_type,
            "fx_rate": str(fx_rate),
            "monthly_revenue_baseline": str(monthly_revenue),
        },
        generated_by=user_id,
        created_at=now,
    )
    db.add(projection)
    await db.flush()

    await logger.ainfo(
        "cashflow_projection_generated",
        scenario=scenario_type,
        months=months,
        net_cashflow=str(net_total),
    )
    return projection


async def get_latest_projection(db: AsyncSession) -> CashflowProjection:
    """Get the most recent cashflow projection."""
    result = await db.execute(
        select(CashflowProjection)
        .order_by(CashflowProjection.created_at.desc())
        .limit(1)
    )
    proj = result.scalar_one_or_none()
    if proj is None:
        raise ProjectionNotFoundError()
    return proj


# ---------------------------------------------------------------------------
# Cash Runway
# ---------------------------------------------------------------------------


async def calculate_cash_runway(db: AsyncSession) -> dict:
    """Calculate current cash runway from latest projection."""
    projection = await get_latest_projection(db)
    buckets = projection.monthly_buckets or []

    if not buckets:
        return {"runway_months": Decimal("0"), "avg_monthly_burn": Decimal("0")}

    burns = [
        Decimal(b["net_cashflow"]) for b in buckets if Decimal(b["net_cashflow"]) < 0
    ]

    if not burns:
        return {
            "runway_months": Decimal("999.0"),
            "avg_monthly_burn": Decimal("0"),
        }

    avg_burn = sum(burns) / len(burns)
    cumulative = Decimal(buckets[-1]["cumulative_cashflow"])

    if cumulative <= 0:
        runway = Decimal("0")
    else:
        runway = (cumulative / abs(avg_burn)).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )

    return {
        "runway_months": runway,
        "avg_monthly_burn": avg_burn.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
    }


# ---------------------------------------------------------------------------
# DSCR
# ---------------------------------------------------------------------------


async def get_current_dscr(db: AsyncSession) -> dict:
    """Calculate DSCR for current month."""
    monthly_revenue = await _calculate_monthly_revenue(db)
    monthly_opex = await _calculate_monthly_operating_costs(db)
    monthly_loan = await _calculate_monthly_loan_payment(db)

    dscr = _calculate_dscr(monthly_revenue, monthly_opex, monthly_loan)

    if dscr < Decimal("1.0"):
        color = "red"
    elif dscr < Decimal("1.5"):
        color = "amber"
    else:
        color = "green"

    return {
        "dscr": dscr,
        "net_operating_income": monthly_revenue - monthly_opex,
        "total_debt_service": monthly_loan,
        "color": color,
    }


# ---------------------------------------------------------------------------
# Stress Scenarios
# ---------------------------------------------------------------------------


def _avg_dscr_from_buckets(buckets: list[dict]) -> Decimal:
    if not buckets:
        return Decimal("0")
    total = sum(Decimal(b["dscr"]) for b in buckets)
    return (total / len(buckets)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _avg_runway_from_buckets(buckets: list[dict]) -> int:
    if not buckets:
        return 0
    total = sum(Decimal(b["cash_runway_months"]) for b in buckets)
    avg = total / len(buckets)
    return int(avg)


def _summarize_projection(proj: CashflowProjection) -> dict:
    buckets = proj.monthly_buckets or []
    avg_dscr = _avg_dscr_from_buckets(buckets)
    last_runway = (
        Decimal(buckets[-1]["cash_runway_months"]) if buckets else Decimal("0")
    )
    last_risk = buckets[-1]["risk_rating"] if buckets else "HIGH"

    return {
        "cash_runway": float(last_runway),
        "avg_dscr": float(avg_dscr),
        "risk_rating": last_risk,
        "net_cashflow": str(proj.net_cashflow),
    }


async def run_stress_scenario(
    db: AsyncSession,
    user_id: uuid.UUID,
    scenario_type: str,
) -> dict:
    """Run stress scenario and compare to base."""
    base_proj = await generate_cashflow_projection(db, user_id, scenario_type="BASE")
    stressed_proj = await generate_cashflow_projection(
        db, user_id, scenario_type=scenario_type
    )

    params = _get_scenario_params(scenario_type)
    scenario = StressScenario(
        name=scenario_type,
        revenue_shock_pct=params["revenue_shock_pct"],
        fx_shock_pct=params["fx_shock_pct"],
        cost_shock_pct=Decimal("0"),
        base_projection_id=base_proj.id,
        stressed_buckets=stressed_proj.monthly_buckets,
        stressed_dscr=_avg_dscr_from_buckets(stressed_proj.monthly_buckets),
        stressed_runway_months=_avg_runway_from_buckets(stressed_proj.monthly_buckets),
        created_by=user_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(scenario)
    await db.flush()

    return {
        "base": _summarize_projection(base_proj),
        "stressed": _summarize_projection(stressed_proj),
    }


async def get_scenarios(db: AsyncSession) -> list[StressScenario]:
    """List all saved scenarios."""
    result = await db.execute(
        select(StressScenario).order_by(StressScenario.created_at.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Liquidity Alerts
# ---------------------------------------------------------------------------


async def check_liquidity_alerts(db: AsyncSession) -> list[dict]:
    """Check for liquidity issues in latest projection."""
    try:
        projection = await get_latest_projection(db)
    except ProjectionNotFoundError:
        return []

    alerts: list[dict] = []
    for bucket in projection.monthly_buckets or []:
        month = bucket["month"]
        net = Decimal(bucket["net_cashflow"])
        dscr = Decimal(bucket["dscr"])
        cumulative = Decimal(bucket["cumulative_cashflow"])
        runway = Decimal(bucket["cash_runway_months"])

        if net < 0:
            severity = "CRITICAL" if cumulative < 0 else "WARNING"
            alerts.append(
                {
                    "month": month,
                    "type": "negative_cashflow",
                    "severity": severity,
                    "message": f"Negative net cashflow of {net} in {month}",
                }
            )

        if dscr < Decimal("1.0"):
            alerts.append(
                {
                    "month": month,
                    "type": "dscr_below_1",
                    "severity": "CRITICAL",
                    "message": f"DSCR of {dscr} below 1.0 in {month}",
                }
            )

        if Decimal("0") < runway < Decimal("4"):
            alerts.append(
                {
                    "month": month,
                    "type": "low_runway",
                    "severity": "CRITICAL" if runway < 2 else "WARNING",
                    "message": f"Cash runway of {runway} months in {month}",
                }
            )

        if cumulative < 0:
            alerts.append(
                {
                    "month": month,
                    "type": "negative_cumulative",
                    "severity": "CRITICAL",
                    "message": (
                        f"Negative cumulative cashflow of {cumulative} in {month}"
                    ),
                }
            )

    return alerts


# ---------------------------------------------------------------------------
# Global Exposure
# ---------------------------------------------------------------------------

EUR_USD_ALERT_THRESHOLD_PCT = Decimal("3")


async def _sum_open_order_usd_obligations(db: AsyncSession) -> Decimal:
    """Sum outstanding USD balance across open orders (not yet delivered).

    Single aggregate query: total_amount - sum(completed payments) per order.
    """

    paid_subq = (
        select(
            OrderPayment.order_id,
            func.coalesce(func.sum(OrderPayment.amount), Decimal("0")).label("paid"),
        )
        .where(OrderPayment.status == PaymentStatus.COMPLETED)
        .group_by(OrderPayment.order_id)
        .subquery()
    )

    result = await db.execute(
        select(
            func.coalesce(
                func.sum(
                    PurchaseOrder.total_amount
                    - func.coalesce(paid_subq.c.paid, Decimal("0"))
                ),
                Decimal("0"),
            )
        )
        .outerjoin(paid_subq, PurchaseOrder.id == paid_subq.c.order_id)
        .where(
            PurchaseOrder.status.in_(
                [
                    OrderStatus.PENDING,
                    OrderStatus.IN_PRODUCTION,
                    OrderStatus.SHIPPING,
                ]
            ),
            PurchaseOrder.currency == "USD",
        )
    )
    return result.scalar() or Decimal("0")


async def _trailing_30d_avg_monthly_revenue_usd(
    db: AsyncSession, ngn_usd_rate: Decimal
) -> Decimal:
    """Calculate trailing 30-day revenue in USD terms."""
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).date()
    result = await db.execute(
        select(func.sum(Sale.total_amount)).where(
            Sale.status == SaleStatus.COMPLETED,
            Sale.sale_date >= thirty_days_ago,
        )
    )
    total_ngn = result.scalar() or Decimal("0")
    if ngn_usd_rate <= 0:
        return Decimal("0")
    return (total_ngn / ngn_usd_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def calculate_global_exposure(db: AsyncSession) -> dict:
    """Calculate global multi-currency exposure in NGN terms.

    total_global_exposure_ngn =
        (usd_obligations × ngn_usd_rate) + (eur_balance × eur_usd_rate × ngn_usd_rate)

    debt_to_trade_ratio =
        eur_balance_usd_equivalent / trailing_30d_avg_monthly_revenue_usd
    """
    # Fetch FX rates
    ngn_usd_rate = await get_latest_rate_value(db, "USDNGN") or DEFAULT_FX_RATE
    raw_eur_usd = await get_latest_rate_value(db, "EURUSD")
    eur_usd_rate_available = raw_eur_usd is not None
    eur_usd_rate = raw_eur_usd or Decimal("0")

    # Derived cross-rate: EUR → NGN = EUR/USD × USD/NGN
    eur_ngn_derived = eur_usd_rate * ngn_usd_rate

    # EUR loan balances
    result = await db.execute(
        select(func.sum(LoanObligation.current_balance)).where(
            LoanObligation.status == LoanStatus.ACTIVE,
            LoanObligation.current_balance_currency == "EUR",
            LoanObligation.current_balance.isnot(None),
        )
    )
    eur_loan_balance = result.scalar() or Decimal("0")

    # Open USD order obligations
    usd_obligations = await _sum_open_order_usd_obligations(db)

    # Total global exposure in NGN
    usd_exposure_ngn = usd_obligations * ngn_usd_rate
    eur_exposure_ngn = eur_loan_balance * eur_usd_rate * ngn_usd_rate
    total_exposure_ngn = (usd_exposure_ngn + eur_exposure_ngn).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # Debt-to-trade ratio
    eur_balance_usd_equiv = eur_loan_balance * eur_usd_rate
    trailing_revenue_usd = await _trailing_30d_avg_monthly_revenue_usd(db, ngn_usd_rate)
    if trailing_revenue_usd > 0:
        debt_to_trade = (eur_balance_usd_equiv / trailing_revenue_usd).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        debt_to_trade = Decimal("0")

    await logger.ainfo(
        "global_exposure_calculated",
        total_ngn=str(total_exposure_ngn),
        eur_balance=str(eur_loan_balance),
        usd_obligations=str(usd_obligations),
    )

    return {
        "eur_loan_balance_eur": eur_loan_balance,
        "eur_usd_rate": eur_usd_rate,
        "eur_usd_rate_available": eur_usd_rate_available,
        "eur_ngn_derived_rate": eur_ngn_derived.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
        "open_order_usd_obligations": usd_obligations,
        "ngn_usd_rate": ngn_usd_rate,
        "total_global_exposure_ngn": total_exposure_ngn,
        "debt_to_trade_ratio": debt_to_trade,
    }


async def check_eur_usd_alert(db: AsyncSession) -> bool:
    """Check if EUR/USD rate changed by more than threshold.

    If so, create a LIQUIDITY recommendation via the AI engine.
    Called from fx.service.ingest_rate when pair == "EURUSD".
    Returns True if an alert was triggered.
    """
    current_rate = await get_latest_rate_value(db, "EURUSD")
    previous_rate = await get_previous_rate_value(db, "EURUSD")

    if current_rate is None or previous_rate is None or previous_rate == 0:
        return False

    pct_change = abs((current_rate / previous_rate - Decimal("1")) * Decimal("100"))

    if pct_change <= EUR_USD_ALERT_THRESHOLD_PCT:
        return False

    # Lazy import to avoid circular dependency: cashflow -> ai_engine
    from src.ai_engine.models import (
        AIRecommendation,
        ActionType,
        RecommendationCategory,
        RecommendationPriority,
        RecommendationStatus,
    )

    # Dedup: skip if a PENDING EURUSD alert already exists
    existing = await db.execute(
        select(func.count())
        .select_from(AIRecommendation)
        .where(
            AIRecommendation.category == RecommendationCategory.CASHFLOW,
            AIRecommendation.action_type == ActionType.FX_LOCK,
            AIRecommendation.status == RecommendationStatus.PENDING,
            AIRecommendation.action_payload["pair"].as_string() == "EURUSD",
        )
    )
    if (existing.scalar() or 0) > 0:
        await logger.ainfo("eur_usd_alert_skipped_duplicate")
        return False

    now = datetime.now(timezone.utc)
    direction = "up" if current_rate > previous_rate else "down"
    rec = AIRecommendation(
        category=RecommendationCategory.CASHFLOW,
        action_type=ActionType.FX_LOCK,
        title=f"EUR/USD moved {pct_change:.1f}% {direction}",
        description=(
            f"EUR/USD rate changed from {previous_rate} to {current_rate} "
            f"({pct_change:.1f}% {direction}). Review EUR-denominated "
            f"loan exposure and consider hedging."
        ),
        priority=RecommendationPriority.HIGH
        if pct_change > Decimal("5")
        else RecommendationPriority.MEDIUM,
        confidence=Decimal("0.85"),
        expected_impact={"eur_usd_change_pct": str(pct_change)},
        action_payload={"pair": "EURUSD", "pct_change": str(pct_change)},
        status=RecommendationStatus.PENDING,
        created_at=now,
        expires_at=now + timedelta(days=7),
    )
    db.add(rec)
    await db.flush()

    await logger.ainfo(
        "eur_usd_alert_triggered",
        pct_change=str(pct_change),
        direction=direction,
    )
    return True


# ---------------------------------------------------------------------------
# Payment Calendar
# ---------------------------------------------------------------------------


def _generate_operating_cost_dates(
    cost: OperatingCost,
    start: date,
    end: date,
) -> list[tuple[date, Decimal]]:
    """Generate payment dates for an operating cost within the horizon."""
    dates: list[tuple[date, Decimal]] = []
    freq = cost.frequency

    if freq == CostFrequency.DAILY:
        delta = timedelta(days=1)
    elif freq == CostFrequency.WEEKLY:
        delta = timedelta(weeks=1)
    elif freq == CostFrequency.MONTHLY:
        delta = timedelta(days=30)
    elif freq == CostFrequency.QUARTERLY:
        delta = timedelta(days=91)
    elif freq == CostFrequency.ANNUALLY:
        delta = timedelta(days=365)
    else:
        delta = timedelta(days=30)

    current = start
    while current <= end:
        dates.append((current, cost.cost_amount))
        current += delta

    return dates


async def build_payment_calendar(
    db: AsyncSession,
    horizon_days: int = 90,
    starting_balance: Decimal | None = None,
) -> dict:
    """Build a payment calendar over the given horizon.

    Returns entries sorted by date with cumulative balance tracking,
    and shortfall detection.
    """
    today = date.today()
    horizon_end = today + timedelta(days=horizon_days)

    entries: list[dict] = []

    # 1. Loan payment schedule entries (unpaid, within horizon)
    loan_result = await db.execute(
        select(LoanPaymentSchedule, LoanObligation.lender_name)
        .join(LoanObligation, LoanPaymentSchedule.loan_id == LoanObligation.id)
        .where(
            LoanPaymentSchedule.is_paid.is_(False),
            LoanPaymentSchedule.due_date >= today,
            LoanPaymentSchedule.due_date <= horizon_end,
        )
        .order_by(LoanPaymentSchedule.due_date)
    )
    for schedule, lender_name in loan_result.all():
        entries.append(
            {
                "date": schedule.due_date,
                "type": "loan_payment",
                "amount": schedule.total_payment,
                "description": f"Loan payment to {lender_name}",
            }
        )

    # 2. Operating cost entries (active, within horizon)
    opex_result = await db.execute(
        select(OperatingCost).where(OperatingCost.is_active.is_(True))
    )
    for cost in opex_result.scalars().all():
        payment_dates = _generate_operating_cost_dates(cost, today, horizon_end)
        for payment_date, amount in payment_dates:
            entries.append(
                {
                    "date": payment_date,
                    "type": "operating_cost",
                    "amount": amount,
                    "description": f"{cost.cost_name} ({cost.category.value})",
                }
            )

    # 3. FX obligations from open purchase orders
    fx_rate = await _get_latest_fx_rate(db)
    fx_result = await db.execute(
        select(PurchaseOrder).where(
            PurchaseOrder.status.in_(
                [
                    OrderStatus.PENDING,
                    OrderStatus.IN_PRODUCTION,
                    OrderStatus.SHIPPING,
                ]
            ),
            PurchaseOrder.currency == "USD",
            PurchaseOrder.expected_delivery_date >= today,
            PurchaseOrder.expected_delivery_date <= horizon_end,
        )
    )
    for order in fx_result.scalars().all():
        paid_result = await db.execute(
            select(func.sum(OrderPayment.amount)).where(
                OrderPayment.order_id == order.id,
                OrderPayment.status == PaymentStatus.COMPLETED,
            )
        )
        paid = paid_result.scalar() or Decimal("0")
        balance_usd = order.total_amount - paid
        balance_ngn = (balance_usd * Decimal("0.70") * fx_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if balance_ngn > 0:
            entries.append(
                {
                    "date": order.expected_delivery_date,
                    "type": "fx_obligation",
                    "amount": balance_ngn,
                    "description": f"FX payment for order (USD balance: {balance_usd})",
                }
            )

    # Sort by date
    entries.sort(key=lambda e: e["date"])

    # Calculate cumulative balance
    if starting_balance is None:
        # Estimate starting balance from latest projection
        try:
            projection = await get_latest_projection(db)
            buckets = projection.monthly_buckets or []
            if buckets:
                starting_balance = Decimal(buckets[0]["cumulative_cashflow"])
            else:
                starting_balance = Decimal("0")
        except ProjectionNotFoundError:
            starting_balance = Decimal("0")

    cumulative = starting_balance
    has_shortfall = False
    first_shortfall_date = None
    total_shortfall = Decimal("0")

    for entry in entries:
        cumulative -= entry["amount"]
        entry["cumulative_balance"] = cumulative.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if cumulative < 0:
            has_shortfall = True
            total_shortfall = min(total_shortfall, cumulative)
            if first_shortfall_date is None:
                first_shortfall_date = entry["date"]

    return {
        "entries": entries,
        "has_shortfall": has_shortfall,
        "first_shortfall_date": first_shortfall_date,
        "total_shortfall": abs(total_shortfall).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
    }


# ---------------------------------------------------------------------------
# Triage Mode
# ---------------------------------------------------------------------------


async def get_active_triage(db: AsyncSession) -> TriageRecord | None:
    """Return the active triage record, or None."""
    result = await db.execute(
        select(TriageRecord)
        .where(TriageRecord.status == TriageStatus.ACTIVE)
        .order_by(TriageRecord.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def check_and_activate_triage(
    db: AsyncSession,
    horizon_days: int = 90,
) -> TriageRecord | None:
    """Check for shortfalls and activate triage if needed.

    Returns the active TriageRecord (existing or newly created), or None
    if no shortfall detected.
    """
    calendar = await build_payment_calendar(db, horizon_days)

    if not calendar["has_shortfall"]:
        # Auto-resolve any active triage
        await auto_resolve_triage(db)
        return None

    # Check if active triage already exists
    existing = await get_active_triage(db)
    if existing is not None:
        # Update shortfall amount if it changed
        existing.shortfall_amount = calendar["total_shortfall"]
        existing.horizon_days = horizon_days
        await db.flush()
        await logger.ainfo(
            "triage_updated",
            triage_id=str(existing.id),
            shortfall=str(calendar["total_shortfall"]),
        )
        return existing

    # Create new triage record
    triage = TriageRecord(
        trigger_date=date.today(),
        shortfall_amount=calendar["total_shortfall"],
        horizon_days=horizon_days,
        status=TriageStatus.ACTIVE,
    )
    db.add(triage)
    await db.flush()

    await logger.ainfo(
        "triage_activated",
        triage_id=str(triage.id),
        shortfall=str(calendar["total_shortfall"]),
        horizon_days=horizon_days,
    )
    return triage


async def auto_resolve_triage(db: AsyncSession) -> bool:
    """Resolve active triage if no shortfall is currently detected.

    Returns True if a triage was resolved.
    """
    active = await get_active_triage(db)
    if active is None:
        return False

    active.status = TriageStatus.RESOLVED
    active.resolution_date = date.today()
    await db.flush()

    await logger.ainfo(
        "triage_auto_resolved",
        triage_id=str(active.id),
    )
    return True


async def generate_triage_recommendations(
    db: AsyncSession,
) -> dict:
    """Generate ranked corrective actions for the active triage.

    Priority order:
    1. LIQUIDATE - sell slow-moving inventory
    2. DELAY_PAYMENT - defer operating costs
    3. ACCELERATE_COLLECTION - flag outstanding receivables
    """
    active = await get_active_triage(db)
    shortfall = active.shortfall_amount if active else Decimal("0")
    triage_id = active.id if active else None

    recommendations: list[dict] = []

    # 1. LIQUIDATE: get liquidation candidates from inventory
    from src.inventory.service import get_liquidation_candidates

    try:
        candidates = await get_liquidation_candidates(db, shortfall)
        total_liquidation_value = sum(c["total_batch_value"] for c in candidates[:5])
        recommendations.append(
            {
                "action_type": "LIQUIDATE",
                "priority": 1,
                "description": (
                    f"Liquidate slow-moving inventory to raise up to "
                    f"{total_liquidation_value} NGN"
                ),
                "estimated_impact": total_liquidation_value,
                "details": [
                    {
                        "batch_id": str(c["batch_id"]),
                        "product_id": str(c["product_id"]),
                        "quantity": c["quantity_remaining"],
                        "batch_value": str(c["total_batch_value"]),
                        "discount_pct": str(c["discount_pct_needed"]),
                    }
                    for c in candidates[:5]
                ],
            }
        )
    except Exception:
        await logger.awarning("triage_liquidation_candidates_failed", exc_info=True)

    # 2. DELAY_PAYMENT: identify deferrable operating costs
    opex_result = await db.execute(
        select(OperatingCost).where(
            OperatingCost.is_active.is_(True),
            OperatingCost.category.in_(["marketing", "transport", "other"]),
        )
    )
    deferrable_costs = list(opex_result.scalars().all())
    total_deferrable = sum(c.monthly_equivalent for c in deferrable_costs)

    if deferrable_costs:
        recommendations.append(
            {
                "action_type": "DELAY_PAYMENT",
                "priority": 2,
                "description": (
                    f"Defer {len(deferrable_costs)} non-essential operating "
                    f"costs to save {total_deferrable} NGN/month"
                ),
                "estimated_impact": total_deferrable,
                "details": [
                    {
                        "cost_id": str(c.id),
                        "cost_name": c.cost_name,
                        "category": c.category.value,
                        "monthly_amount": str(c.monthly_equivalent),
                    }
                    for c in deferrable_costs
                ],
            }
        )

    # 3. ACCELERATE_COLLECTION: flag outstanding receivables (pending sales)
    pending_result = await db.execute(
        select(
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.total_amount), Decimal("0")),
        ).where(Sale.status == SaleStatus.PENDING)
    )
    row = pending_result.one()
    pending_count = row[0] or 0
    pending_total = row[1] or Decimal("0")

    if pending_count > 0:
        recommendations.append(
            {
                "action_type": "ACCELERATE_COLLECTION",
                "priority": 3,
                "description": (
                    f"Collect {pending_count} outstanding receivables "
                    f"totaling {pending_total} NGN"
                ),
                "estimated_impact": pending_total,
                "details": None,
            }
        )

    return {
        "triage_id": triage_id,
        "shortfall_amount": shortfall,
        "recommendations": recommendations,
    }
