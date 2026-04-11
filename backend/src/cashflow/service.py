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
    LoanStatus,
    OperatingCost,
    StressScenario,
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


async def create_loan(
    db: AsyncSession, data, user_id: uuid.UUID
) -> LoanObligation:
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
        select(LoanObligation).where(
            LoanObligation.status == LoanStatus.ACTIVE
        )
    )
    return list(result.scalars().all())


async def get_loan(
    db: AsyncSession, loan_id: uuid.UUID
) -> LoanObligation:
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
    return (amount * multiplier).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


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
            PurchaseOrder.status.in_([
                OrderStatus.PENDING,
                OrderStatus.IN_PRODUCTION,
                OrderStatus.SHIPPING,
            ]),
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
    return (noi / loan_payment).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )


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

        monthly_buckets.append({
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
        })

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
        Decimal(b["net_cashflow"])
        for b in buckets
        if Decimal(b["net_cashflow"]) < 0
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
        "avg_monthly_burn": avg_burn.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
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
    return (total / len(buckets)).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )


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
    base_proj = await generate_cashflow_projection(
        db, user_id, scenario_type="BASE"
    )
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
        stressed_runway_months=_avg_runway_from_buckets(
            stressed_proj.monthly_buckets
        ),
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
            alerts.append({
                "month": month,
                "type": "negative_cashflow",
                "severity": severity,
                "message": f"Negative net cashflow of {net} in {month}",
            })

        if dscr < Decimal("1.0"):
            alerts.append({
                "month": month,
                "type": "dscr_below_1",
                "severity": "CRITICAL",
                "message": f"DSCR of {dscr} below 1.0 in {month}",
            })

        if Decimal("0") < runway < Decimal("4"):
            alerts.append({
                "month": month,
                "type": "low_runway",
                "severity": "CRITICAL" if runway < 2 else "WARNING",
                "message": f"Cash runway of {runway} months in {month}",
            })

        if cumulative < 0:
            alerts.append({
                "month": month,
                "type": "negative_cumulative",
                "severity": "CRITICAL",
                "message": (
                    f"Negative cumulative cashflow of {cumulative} in {month}"
                ),
            })

    return alerts


# ---------------------------------------------------------------------------
# Global Exposure
# ---------------------------------------------------------------------------

EUR_USD_ALERT_THRESHOLD_PCT = Decimal("3")


async def _sum_open_order_usd_obligations(db: AsyncSession) -> Decimal:
    """Sum outstanding USD balance across open orders (not yet delivered)."""
    result = await db.execute(
        select(
            PurchaseOrder.id,
            PurchaseOrder.total_amount,
        ).where(
            PurchaseOrder.status.in_([
                OrderStatus.PENDING,
                OrderStatus.IN_PRODUCTION,
                OrderStatus.SHIPPING,
            ]),
            PurchaseOrder.currency == "USD",
        )
    )
    orders = result.all()
    total = Decimal("0")
    for order_id, total_amount in orders:
        paid_result = await db.execute(
            select(func.sum(OrderPayment.amount)).where(
                OrderPayment.order_id == order_id,
                OrderPayment.status == PaymentStatus.COMPLETED,
            )
        )
        paid = paid_result.scalar() or Decimal("0")
        total += total_amount - paid
    return total


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
    return (total_ngn / ngn_usd_rate).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


async def calculate_global_exposure(db: AsyncSession) -> dict:
    """Calculate global multi-currency exposure in NGN terms.

    total_global_exposure_ngn =
        (usd_obligations × ngn_usd_rate) + (eur_balance × eur_usd_rate × ngn_usd_rate)

    debt_to_trade_ratio =
        eur_balance_usd_equivalent / trailing_30d_avg_monthly_revenue_usd
    """
    # Fetch FX rates
    ngn_usd_rate = await get_latest_rate_value(db, "USDNGN") or DEFAULT_FX_RATE
    eur_usd_rate = await get_latest_rate_value(db, "EURUSD") or Decimal("1.080000")

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
    trailing_revenue_usd = await _trailing_30d_avg_monthly_revenue_usd(
        db, ngn_usd_rate
    )
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
    Returns True if an alert was triggered.
    """
    current_rate = await get_latest_rate_value(db, "EURUSD")
    previous_rate = await get_previous_rate_value(db, "EURUSD")

    if current_rate is None or previous_rate is None or previous_rate == 0:
        return False

    pct_change = abs(
        (current_rate / previous_rate - Decimal("1")) * Decimal("100")
    )

    if pct_change <= EUR_USD_ALERT_THRESHOLD_PCT:
        return False

    # Create a LIQUIDITY recommendation
    try:
        from src.ai_engine.models import (
            AIRecommendation,
            ActionType,
            RecommendationCategory,
            RecommendationPriority,
            RecommendationStatus,
        )

        now = datetime.now(timezone.utc)
        direction = "up" if current_rate > previous_rate else "down"
        rec = AIRecommendation(
            category=RecommendationCategory.CASHFLOW,
            action_type=ActionType.COST_CUT,
            title=f"EUR/USD moved {pct_change:.1f}% {direction}",
            description=(
                f"EUR/USD rate changed from {previous_rate} to {current_rate} "
                f"({pct_change:.1f}% {direction}). Review EUR-denominated "
                f"loan exposure and consider hedging."
            ),
            priority=RecommendationPriority.HIGH if pct_change > Decimal("5") else RecommendationPriority.MEDIUM,
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
    except Exception:
        await logger.aerror("eur_usd_alert_failed", exc_info=True)
        return False
