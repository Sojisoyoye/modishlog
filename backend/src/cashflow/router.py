"""Cashflow API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.cashflow.exceptions import (
    InvalidScenarioTypeError,
    LoanNotFoundError,
    ProjectionNotFoundError,
)
from src.cashflow.schemas import (
    AlertResponse,
    DSCRResponse,
    GlobalExposureResponse,
    LoanCreate,
    LoanRead,
    OperatingCostCreate,
    OperatingCostRead,
    ProjectionRead,
    RunwayResponse,
    ScenarioComparisonResponse,
    ScenarioRead,
    ScenarioRequest,
)
from src.cashflow.service import (
    VALID_SCENARIO_TYPES,
    calculate_cash_runway,
    calculate_global_exposure,
    check_eur_usd_alert,
    check_liquidity_alerts,
    create_loan,
    create_operating_cost,
    generate_cashflow_projection,
    get_current_dscr,
    get_latest_projection,
    get_loan,
    get_loans,
    get_operating_costs,
    get_scenarios,
    run_stress_scenario,
)
from src.core.database import get_db

router = APIRouter()


# ---------------------------------------------------------------------------
# Loan Obligations
# ---------------------------------------------------------------------------


@router.post("/loans", response_model=LoanRead, status_code=status.HTTP_201_CREATED)
async def create_loan_endpoint(
    body: LoanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Register a new loan obligation."""
    return await create_loan(db, body, current_user.id)


@router.get("/loans", response_model=list[LoanRead])
async def list_loans_endpoint(db: AsyncSession = Depends(get_db)):
    """List active loan obligations."""
    return await get_loans(db)


@router.get("/loans/{loan_id}", response_model=LoanRead)
async def get_loan_endpoint(
    loan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific loan obligation."""
    try:
        return await get_loan(db, loan_id)
    except LoanNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


# ---------------------------------------------------------------------------
# Operating Costs
# ---------------------------------------------------------------------------


@router.post(
    "/operating-costs",
    response_model=OperatingCostRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_operating_cost_endpoint(
    body: OperatingCostCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a recurring operating cost."""
    return await create_operating_cost(db, body, current_user.id)


@router.get("/operating-costs", response_model=list[OperatingCostRead])
async def list_operating_costs_endpoint(db: AsyncSession = Depends(get_db)):
    """List active operating costs."""
    return await get_operating_costs(db)


# ---------------------------------------------------------------------------
# Cashflow Projection
# ---------------------------------------------------------------------------


@router.get("/projection", response_model=ProjectionRead)
async def get_projection_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get the latest 6-month cashflow projection (generates if none exists)."""
    try:
        return await get_latest_projection(db)
    except ProjectionNotFoundError:
        return await generate_cashflow_projection(db, current_user.id)


@router.get("/projection/{scenario}", response_model=ProjectionRead)
async def get_scenario_projection_endpoint(
    scenario: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Generate a cashflow projection for a specific scenario."""
    if scenario.upper() not in VALID_SCENARIO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(InvalidScenarioTypeError(scenario)),
        )
    return await generate_cashflow_projection(
        db, current_user.id, scenario_type=scenario.upper()
    )


# ---------------------------------------------------------------------------
# Stress Scenarios
# ---------------------------------------------------------------------------


@router.post("/run-scenario", response_model=ScenarioComparisonResponse)
async def run_scenario_endpoint(
    body: ScenarioRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Run a stress scenario simulation and compare to base."""
    if body.scenario_type.upper() not in VALID_SCENARIO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(InvalidScenarioTypeError(body.scenario_type)),
        )
    result = await run_stress_scenario(
        db, current_user.id, body.scenario_type.upper()
    )
    return ScenarioComparisonResponse(**result)


@router.get("/scenarios", response_model=list[ScenarioRead])
async def list_scenarios_endpoint(db: AsyncSession = Depends(get_db)):
    """List saved stress scenario simulations."""
    return await get_scenarios(db)


# ---------------------------------------------------------------------------
# Cash Runway
# ---------------------------------------------------------------------------


@router.get("/cash-runway", response_model=RunwayResponse)
async def cash_runway_endpoint(db: AsyncSession = Depends(get_db)):
    """Get current cash runway in months."""
    try:
        data = await calculate_cash_runway(db)
        return RunwayResponse(**data)
    except ProjectionNotFoundError:
        return RunwayResponse(runway_months=0, avg_monthly_burn=0)


# ---------------------------------------------------------------------------
# DSCR
# ---------------------------------------------------------------------------


@router.get("/dscr", response_model=DSCRResponse)
async def dscr_endpoint(db: AsyncSession = Depends(get_db)):
    """Get current Debt Service Coverage Ratio."""
    data = await get_current_dscr(db)
    return DSCRResponse(**data)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


@router.get("/alerts", response_model=list[AlertResponse])
async def alerts_endpoint(db: AsyncSession = Depends(get_db)):
    """Get liquidity shortage alerts."""
    alerts = await check_liquidity_alerts(db)
    return [AlertResponse(**a) for a in alerts]


# ---------------------------------------------------------------------------
# Global Exposure
# ---------------------------------------------------------------------------


@router.get("/global-exposure", response_model=GlobalExposureResponse)
async def global_exposure_endpoint(db: AsyncSession = Depends(get_db)):
    """Get multi-currency global exposure summary (EUR/USD/NGN)."""
    data = await calculate_global_exposure(db)
    # Also check EUR/USD alert threshold
    await check_eur_usd_alert(db)
    return GlobalExposureResponse(**data)
