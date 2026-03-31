"""AI Engine API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_engine.exceptions import (
    RecommendationAlreadyProcessedError,
    RecommendationExpiredError,
    RecommendationNotFoundError,
    ReorderSuggestionNotFoundError,
    USDStrategyConfigNotFoundError,
)
from src.ai_engine.schemas import (
    ImpactSummary,
    RecommendationAccept,
    RecommendationDismiss,
    RecommendationListResponse,
    RecommendationRead,
    ReorderSuggestionListResponse,
    ReorderSuggestionRead,
    USDAccumulationScheduleResponse,
    USDStrategyConfigCreate,
    USDStrategyConfigRead,
)
from src.ai_engine.service import (
    apply_recommendation,
    approve_reorder,
    dismiss_recommendation,
    generate_all_recommendations,
    generate_reorder_suggestions,
    generate_usd_accumulation_schedule,
    get_impact_summary,
    get_recommendation,
    get_recommendation_history,
    get_recommendations,
    get_reorder_suggestion,
    get_reorder_suggestions,
    get_usd_strategy_config,
    update_usd_strategy_config,
)
from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.core.database import get_db

router = APIRouter()


# ---------------------------------------------------------------------------
# Unified Recommendations
# ---------------------------------------------------------------------------


@router.post(
    "/recommendations/generate",
    response_model=list[RecommendationRead],
    status_code=status.HTTP_201_CREATED,
)
async def generate_recommendations_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Generate unified AI recommendations across all domains."""
    recs = await generate_all_recommendations(db, current_user.id)
    return recs


@router.get("/recommendations", response_model=RecommendationListResponse)
async def list_recommendations_endpoint(
    category: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get recommendations with optional category and status filters."""
    recs = await get_recommendations(db, category, status_filter, limit)

    by_category: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    for r in recs:
        cat = r.category if isinstance(r.category, str) else r.category.value
        by_category[cat] = by_category.get(cat, 0) + 1
        pri = r.priority if isinstance(r.priority, str) else r.priority.value
        by_priority[pri] = by_priority.get(pri, 0) + 1

    return RecommendationListResponse(
        items=recs,
        total=len(recs),
        by_category=by_category,
        by_priority=by_priority,
    )


@router.get(
    "/recommendations/impact",
    response_model=ImpactSummary,
)
async def impact_summary_endpoint(db: AsyncSession = Depends(get_db)):
    """Get projected impact summary of all pending recommendations."""
    data = await get_impact_summary(db)
    return ImpactSummary(**data)


@router.get(
    "/recommendations/history",
    response_model=list[RecommendationRead],
)
async def recommendation_history_endpoint(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get applied/dismissed recommendation history."""
    return await get_recommendation_history(db, limit)


@router.get(
    "/recommendations/{recommendation_id}",
    response_model=RecommendationRead,
)
async def get_recommendation_endpoint(
    recommendation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific recommendation by ID."""
    try:
        return await get_recommendation(db, recommendation_id)
    except RecommendationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


@router.post(
    "/recommendations/{recommendation_id}/apply",
    response_model=RecommendationRead,
)
async def apply_recommendation_endpoint(
    recommendation_id: uuid.UUID,
    body: RecommendationAccept | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Apply a recommendation."""
    try:
        notes = body.notes if body else None
        return await apply_recommendation(
            db, recommendation_id, current_user.id, notes
        )
    except RecommendationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )
    except RecommendationAlreadyProcessedError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(e)
        )
    except RecommendationExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail=str(e)
        )


@router.post(
    "/recommendations/{recommendation_id}/dismiss",
    response_model=RecommendationRead,
)
async def dismiss_recommendation_endpoint(
    recommendation_id: uuid.UUID,
    body: RecommendationDismiss,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Dismiss a recommendation with a reason."""
    try:
        return await dismiss_recommendation(
            db, recommendation_id, current_user.id, body.reason
        )
    except RecommendationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )
    except RecommendationAlreadyProcessedError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(e)
        )


# ---------------------------------------------------------------------------
# USD Accumulation
# ---------------------------------------------------------------------------


@router.get(
    "/usd-accumulation/{order_id}",
    response_model=USDAccumulationScheduleResponse,
)
async def usd_accumulation_schedule_endpoint(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get USD accumulation schedule for a specific order."""
    try:
        data = await generate_usd_accumulation_schedule(db, order_id)
        return USDAccumulationScheduleResponse(**data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


@router.get(
    "/usd-strategy/config",
    response_model=USDStrategyConfigRead,
)
async def get_usd_strategy_config_endpoint(
    db: AsyncSession = Depends(get_db),
):
    """Get current USD strategy configuration."""
    try:
        return await get_usd_strategy_config(db)
    except USDStrategyConfigNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


@router.post(
    "/usd-strategy/config",
    response_model=USDStrategyConfigRead,
    status_code=status.HTTP_201_CREATED,
)
async def update_usd_strategy_config_endpoint(
    body: USDStrategyConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create or update USD strategy configuration."""
    return await update_usd_strategy_config(db, body, current_user.id)


# ---------------------------------------------------------------------------
# Reorder Suggestions
# ---------------------------------------------------------------------------


@router.post(
    "/reorder/generate",
    response_model=list[ReorderSuggestionRead],
    status_code=status.HTTP_201_CREATED,
)
async def generate_reorder_suggestions_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Generate reorder suggestions for all products."""
    return await generate_reorder_suggestions(db)


@router.get("/reorder", response_model=ReorderSuggestionListResponse)
async def list_reorder_suggestions_endpoint(
    db: AsyncSession = Depends(get_db),
):
    """Get all pending reorder suggestions."""
    suggestions = await get_reorder_suggestions(db)
    critical_count = sum(
        1 for s in suggestions
        if s.estimated_stockout_date
        and (s.estimated_stockout_date - s.created_at.date()).days < 14
    )
    return ReorderSuggestionListResponse(
        items=suggestions,
        total=len(suggestions),
        critical_count=critical_count,
    )


@router.get(
    "/reorder/{product_id}",
    response_model=ReorderSuggestionRead,
)
async def get_reorder_suggestion_endpoint(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get reorder suggestion for a specific product."""
    try:
        return await get_reorder_suggestion(db, product_id)
    except ReorderSuggestionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


@router.post(
    "/reorder/{product_id}/approve",
    response_model=ReorderSuggestionRead,
)
async def approve_reorder_endpoint(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Approve a reorder suggestion."""
    try:
        return await approve_reorder(db, product_id)
    except ReorderSuggestionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )
