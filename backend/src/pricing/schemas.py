# TODO: Pydantic schemas for the Pricing domain
#
# --- Demand Elasticity Schemas ---
# ElasticityRead
#   - product_id: UUID
#   - product_name: str
#   - elasticity_coefficient: Decimal
#   - classification: str ("elastic" | "inelastic" | "unit_elastic")
#   - r_squared: Decimal
#   - data_points_used: int
#   - calculation_date: date
#
# ElasticityCurve
#   - product_id: UUID
#   - price_points: list[dict] (price: Decimal, estimated_demand: int)
#   - optimal_price: Decimal (revenue-maximizing price)
#   - optimal_demand: int
#
# --- Margin Schemas ---
# MarginAnalysis
#   - product_id: UUID
#   - product_name: str
#   - unit_cost: Decimal
#   - selling_price: Decimal
#   - current_margin_pct: float
#   - target_margin_pct: float | None
#   - margin_gap: float (current - target)
#   - volume_last_30d: int
#   - revenue_contribution_pct: float
#
# PortfolioOptimization
#   - total_products: int
#   - current_portfolio_margin: Decimal
#   - optimized_portfolio_margin: Decimal
#   - improvement_pct: float
#   - price_changes: list[dict] (product_id, current_price, suggested_price, margin_impact)
#
# MarginTargetCreate
#   - product_id: UUID | None
#   - category_id: UUID | None
#   - target_margin_pct: Decimal
#   - min_margin_pct: Decimal
#   - priority: int = 1
#
# MarginTargetRead
#   - id: UUID
#   - product_id: UUID | None
#   - category_id: UUID | None
#   - target_margin_pct: Decimal
#   - min_margin_pct: Decimal
#   - priority: int
#   - set_by: UUID
#
# --- Pricing Recommendation Schemas ---
# RecommendationRead
#   - id: UUID
#   - product_id: UUID
#   - product_name: str
#   - current_price: Decimal
#   - recommended_price: Decimal
#   - price_change_pct: float
#   - expected_demand_change_pct: Decimal
#   - expected_revenue_change_pct: Decimal
#   - expected_margin_change_pct: Decimal
#   - confidence: Decimal
#   - reasoning: str
#   - status: str
#   - created_at: datetime
#
# RecommendationApplyRequest
#   - recommendation_ids: list[UUID] (which recommendations to apply)
#
# RecommendationHistoryRead
#   - id: UUID
#   - product_id: UUID
#   - old_price: Decimal
#   - new_price: Decimal
#   - applied_at: datetime
#   - actual_demand_change_pct: Decimal | None (measured after application)
#   - actual_revenue_change_pct: Decimal | None
#
# --- Cross-Subsidization Schemas ---
# CrossSubsidyRead
#   - analysis_date: date
#   - portfolio_total_margin: Decimal
#   - high_margin_products: list[dict] (product_id, name, margin_pct, subsidy_contribution)
#   - low_margin_products: list[dict] (product_id, name, margin_pct, subsidy_received)
#   - recommendations: list[dict] (product_id, action, reasoning)
#
# SubsidyMatrix
#   - products: list[dict] (product_id, name, margin_pct)
#   - flows: list[dict] (from_product_id, to_product_id, subsidy_amount)
#
# SubsidySimulationRequest
#   - price_changes: list[dict] (product_id, new_price)
#
# SubsidySimulationResult
#   - before: CrossSubsidyRead
#   - after: CrossSubsidyRead
#   - impact_summary: dict (portfolio_margin_delta, subsidy_flow_changes)
