"""Pricing API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user, get_current_business_id
from src.auth.models import User
from src.core.database import get_db
from src.fx.exceptions import FXPairNotFoundError
from src.pricing.exceptions import (
    CrossSubsidyAnalysisError,
    ElasticityNotFoundError,
    InsufficientPriceDataError,
    MixTargetSumError,
    OptimizationInfeasibleError,
    PricingSuggestionError,
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
    MixStatusResponse,
    MixTargetBulkCreate,
    MixTargetRead,
    PortfolioMarginResponse,
    PriceSuggestionRead,
    RecommendationRead,
    ScenarioCreate,
    ScenarioRead,
    SellingPriceSuggestionRequest,
    SellingPriceSuggestionResponse,
    SensitivityCalcRequest,
    SensitivityCalcResponse,
    SuggestRequest,
)
from src.pricing.service import (
    analyze_cross_subsidization,
    apply_recommendation,
    calculate_demand_forecast,
    calculate_portfolio_margin,
    calculate_price_elasticity_impact,
    compute_suggestion,
    dismiss_recommendation,
    generate_recommendations,
    get_elasticity,
    get_margin_targets,
    get_mix_status,
    get_recommendations,
    get_selling_price_suggestion,
    get_suggestion_history,
    list_scenarios,
    save_scenario,
    sensitivity_calc,
    set_margin_target,
    update_elasticity_config,
    upsert_mix_targets,
)

router = APIRouter(dependencies=[Depends(get_current_active_user)])


# ---------------------------------------------------------------------------
# Portfolio Margin
# ---------------------------------------------------------------------------


@router.get("/portfolio-margin", response_model=PortfolioMarginResponse)
async def portfolio_margin_endpoint(
    db: AsyncSession = Depends(get_db),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Get current blended margin and per-product breakdown."""
    data = await calculate_portfolio_margin(db, business_id=business_id)
    return PortfolioMarginResponse(**data)


# ---------------------------------------------------------------------------
# Pricing Recommendations
# ---------------------------------------------------------------------------


@router.get("/recommendations", response_model=list[RecommendationRead])
async def list_recommendations_endpoint(
    db: AsyncSession = Depends(get_db),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Get active pricing recommendations."""
    return await get_recommendations(db, business_id=business_id)


@router.post(
    "/recommendations/generate",
    response_model=list[RecommendationRead],
    status_code=status.HTTP_201_CREATED,
)
async def generate_recommendations_endpoint(
    body: GenerateRecommendationsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Generate pricing recommendations based on target margin."""
    try:
        return await generate_recommendations(db, business_id=business_id, target_margin=body.target_margin)
    except OptimizationInfeasibleError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/recommendations/{rec_id}/apply",
    response_model=RecommendationRead,
)
async def apply_recommendation_endpoint(
    rec_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Apply a pricing recommendation."""
    try:
        return await apply_recommendation(db, rec_id, current_user.id, business_id=business_id)
    except RecommendationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RecommendationExpiredError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/recommendations/{rec_id}/dismiss",
    response_model=RecommendationRead,
)
async def dismiss_recommendation_endpoint(
    rec_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Dismiss a pricing recommendation."""
    try:
        return await dismiss_recommendation(db, rec_id, business_id=business_id)
    except RecommendationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


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
    return await update_elasticity_config(db, product_id, body.elasticity_coefficient)


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
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Set a target margin for a product or category."""
    return await set_margin_target(db, body, current_user.id, business_id=business_id)


@router.get("/margins/target", response_model=list[MarginTargetRead])
async def list_margin_targets_endpoint(
    db: AsyncSession = Depends(get_db),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """View current margin targets."""
    return await get_margin_targets(db, business_id=business_id)


# ---------------------------------------------------------------------------
# Product Mix Targets
# ---------------------------------------------------------------------------


@router.post(
    "/mix-targets",
    response_model=list[MixTargetRead],
    status_code=status.HTTP_200_OK,
)
async def upsert_mix_targets_endpoint(
    body: MixTargetBulkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Bulk upsert product mix targets (must sum to 100%)."""
    try:
        targets_data = [
            {"category_id": t.category_id, "target_pct": t.target_pct}
            for t in body.targets
        ]
        return await upsert_mix_targets(db, targets_data, business_id=business_id)
    except MixTargetSumError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/mix-status", response_model=MixStatusResponse)
async def mix_status_endpoint(
    days: int = 90,
    db: AsyncSession = Depends(get_db),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Get actual vs target product mix status."""
    statuses = await get_mix_status(db, days, business_id=business_id)
    return MixStatusResponse(categories=statuses)


# ---------------------------------------------------------------------------
# Cross-Subsidization
# ---------------------------------------------------------------------------


@router.get("/cross-subsidy", response_model=CrossSubsidyRead)
async def cross_subsidy_endpoint(
    db: AsyncSession = Depends(get_db),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Analyze cross-subsidization across portfolio."""
    try:
        return await analyze_cross_subsidization(db, business_id=business_id)
    except CrossSubsidyAnalysisError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ---------------------------------------------------------------------------
# Price-FX Sensitivity Playground
# ---------------------------------------------------------------------------


@router.post("/sensitivity-calc", response_model=SensitivityCalcResponse)
async def sensitivity_calc_endpoint(
    body: SensitivityCalcRequest,
    db: AsyncSession = Depends(get_db),
):
    """Stateless price-FX sensitivity calculation."""
    try:
        data = await sensitivity_calc(
            db,
            selling_price=body.selling_price_override,
            fx_rate=body.fx_rate_override,
            quantity=body.quantity,
            product_id=body.product_id,
            unit_cost_usd_override=body.unit_cost_usd,
        )
        return SensitivityCalcResponse(**data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/selling-price-suggestion", response_model=SellingPriceSuggestionResponse)
async def selling_price_suggestion_endpoint(
    body: SellingPriceSuggestionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Return the FX-adjusted minimum selling price for a given cost and margin target."""
    try:
        data = await get_selling_price_suggestion(
            db,
            product_id=body.product_id,
            unit_cost_override=body.unit_cost_override,
            currency=body.currency,
            fx_rate_override=body.fx_rate_override,
            min_margin_pct=body.min_margin_pct,
        )
        return SellingPriceSuggestionResponse(**data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except FXPairNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No FX rate found for currency pair: {e}",
        )


@router.post(
    "/scenarios",
    response_model=ScenarioRead,
    status_code=status.HTTP_201_CREATED,
)
async def save_scenario_endpoint(
    body: ScenarioCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Save a pricing scenario (max 10 per user)."""
    return await save_scenario(
        db,
        name=body.name,
        user_id=current_user.id,
        business_id=business_id,
        selling_price=body.selling_price,
        fx_rate=body.fx_rate,
        quantity=body.quantity,
        product_id=body.product_id,
        results=body.results,
    )


@router.get("/scenarios", response_model=list[ScenarioRead])
async def list_scenarios_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """List saved pricing scenarios for the current user."""
    return await list_scenarios(db, current_user.id, business_id=business_id)


# ---------------------------------------------------------------------------
# Lot-based price suggestion (Task #76) — static paths before /{product_id}
# ---------------------------------------------------------------------------


@router.post(
    "/suggest/{product_id}",
    response_model=PriceSuggestionRead,
    status_code=status.HTTP_201_CREATED,
)
async def compute_suggestion_endpoint(
    product_id: uuid.UUID,
    body: SuggestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Compute and persist a sell-price suggestion from active lot cost basis."""
    try:
        return await compute_suggestion(
            db, product_id, target_margin=body.target_margin_pct
        )
    except PricingSuggestionError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )


@router.get("/suggest/{product_id}/history", response_model=list[PriceSuggestionRead])
async def suggestion_history_endpoint(
    product_id: uuid.UUID,
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return the last N price suggestions for a product, newest first."""
    return await get_suggestion_history(db, product_id, limit=limit)
