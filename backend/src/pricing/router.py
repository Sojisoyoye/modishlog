"""Pricing API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.core.database import get_db
from src.pricing.exceptions import (
    CrossSubsidyAnalysisError,
    ElasticityNotFoundError,
    InsufficientPriceDataError,
    OptimizationInfeasibleError,
    RecommendationExpiredError,
    RecommendationNotFoundError,
)
from src.pricing.schemas import (
    CrossSubsidyRead,
    DemandForecastResponse,
    ElasticityConfigUpdate,
    ElasticityRead,
    GenerateRecommendationsRequest,
    MarginTargetCreate,
    MarginTargetRead,
    PortfolioMarginResponse,
    RecommendationRead,
)
from src.pricing.service import (
    analyze_cross_subsidization,
    apply_recommendation,
    calculate_demand_forecast,
    calculate_portfolio_margin,
    calculate_price_elasticity_impact,
    dismiss_recommendation,
    generate_recommendations,
    get_elasticity,
    get_margin_targets,
    get_recommendations,
    set_margin_target,
    update_elasticity_config,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Portfolio Margin
# ---------------------------------------------------------------------------


@router.get("/portfolio-margin", response_model=PortfolioMarginResponse)
async def portfolio_margin_endpoint(db: AsyncSession = Depends(get_db)):
    """Get current blended margin and per-product breakdown."""
    data = await calculate_portfolio_margin(db)
    return PortfolioMarginResponse(**data)


# ---------------------------------------------------------------------------
# Pricing Recommendations
# ---------------------------------------------------------------------------


@router.get("/recommendations", response_model=list[RecommendationRead])
async def list_recommendations_endpoint(db: AsyncSession = Depends(get_db)):
    """Get active pricing recommendations."""
    return await get_recommendations(db)


@router.post(
    "/recommendations/generate",
    response_model=list[RecommendationRead],
    status_code=status.HTTP_201_CREATED,
)
async def generate_recommendations_endpoint(
    body: GenerateRecommendationsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Generate pricing recommendations based on target margin."""
    try:
        return await generate_recommendations(db, body.target_margin)
    except OptimizationInfeasibleError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )


@router.post(
    "/recommendations/{rec_id}/apply",
    response_model=RecommendationRead,
)
async def apply_recommendation_endpoint(
    rec_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Apply a pricing recommendation."""
    try:
        return await apply_recommendation(db, rec_id, current_user.id)
    except RecommendationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )
    except RecommendationExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )


@router.post(
    "/recommendations/{rec_id}/dismiss",
    response_model=RecommendationRead,
)
async def dismiss_recommendation_endpoint(
    rec_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Dismiss a pricing recommendation."""
    try:
        return await dismiss_recommendation(db, rec_id)
    except RecommendationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


# ---------------------------------------------------------------------------
# Demand Forecast
# ---------------------------------------------------------------------------


@router.get(
    "/demand-forecast/{product_id}",
    response_model=DemandForecastResponse,
)
async def demand_forecast_endpoint(
    product_id: uuid.UUID,
    horizon_days: int = 90,
    db: AsyncSession = Depends(get_db),
):
    """Get demand forecast for a product."""
    try:
        data = await calculate_demand_forecast(db, product_id, horizon_days)
        return DemandForecastResponse(**data)
    except InsufficientPriceDataError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )


# ---------------------------------------------------------------------------
# Elasticity Configuration
# ---------------------------------------------------------------------------


@router.get(
    "/elasticity/{product_id}",
    response_model=ElasticityRead,
)
async def get_elasticity_endpoint(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get elasticity data for a product."""
    try:
        return await get_elasticity(db, product_id)
    except ElasticityNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


@router.post(
    "/configure-elasticity/{product_id}",
    response_model=ElasticityRead,
)
async def configure_elasticity_endpoint(
    product_id: uuid.UUID,
    body: ElasticityConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update elasticity coefficient for a product."""
    return await update_elasticity_config(
        db, product_id, body.elasticity_coefficient
    )


@router.get("/elasticity-impact/{product_id}")
async def elasticity_impact_endpoint(
    product_id: uuid.UUID,
    proposed_price: float,
    db: AsyncSession = Depends(get_db),
):
    """Calculate demand impact for a proposed price change."""
    from decimal import Decimal

    return await calculate_price_elasticity_impact(
        db, product_id, Decimal(str(proposed_price))
    )


# ---------------------------------------------------------------------------
# Margin Targets
# ---------------------------------------------------------------------------


@router.post(
    "/margins/target",
    response_model=MarginTargetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_margin_target_endpoint(
    body: MarginTargetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Set a target margin for a product or category."""
    return await set_margin_target(db, body, current_user.id)


@router.get("/margins/target", response_model=list[MarginTargetRead])
async def list_margin_targets_endpoint(db: AsyncSession = Depends(get_db)):
    """View current margin targets."""
    return await get_margin_targets(db)


# ---------------------------------------------------------------------------
# Cross-Subsidization
# ---------------------------------------------------------------------------


@router.get("/cross-subsidy", response_model=CrossSubsidyRead)
async def cross_subsidy_endpoint(
    db: AsyncSession = Depends(get_db),
):
    """Analyze cross-subsidization across portfolio."""
    try:
        return await analyze_cross_subsidization(db)
    except CrossSubsidyAnalysisError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
