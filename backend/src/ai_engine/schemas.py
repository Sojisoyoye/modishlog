# TODO: Pydantic schemas for the AI Engine domain
#
# --- Unified Recommendation Schemas ---
# RecommendationRead
#   - id: UUID
#   - category: str
#   - title: str
#   - description: str
#   - priority: str
#   - confidence: Decimal
#   - expected_impact: dict (metric, current_value, projected_value, change_pct)
#   - action_type: str
#   - reference_id: UUID | None
#   - reference_type: str | None
#   - status: str
#   - created_at: datetime
#   - expires_at: datetime
#
# RecommendationListResponse
#   - items: list[RecommendationRead]
#   - total: int
#   - by_category: dict[str, int] (count per category)
#   - by_priority: dict[str, int] (count per priority)
#
# RecommendationAccept
#   - notes: str | None
#
# RecommendationDismiss
#   - reason: str (required)
#
# ImpactSummary
#   - total_pending: int
#   - projected_revenue_impact: Decimal
#   - projected_cost_savings: Decimal
#   - projected_margin_improvement_pct: float
#   - by_category: list[dict] (category, count, projected_impact)
#
# RecommendationHistory
#   - id: UUID
#   - category, title, action_type, status
#   - accepted_at: datetime | None
#   - measured_outcome: dict | None (metric, actual_value, expected_value, accuracy_pct)
#
# --- USD Accumulation Strategy Schemas ---
# USDStrategyRead
#   - target_usd_balance: Decimal
#   - current_usd_balance: Decimal
#   - gap_amount: Decimal (target - current)
#   - gap_pct: float
#   - current_fx_rate: Decimal
#   - strategy_summary: str (AI-generated narrative)
#   - next_recommended_action: str
#
# USDScheduleRead
#   - id: UUID
#   - recommended_date: date
#   - recommended_amount_usd: Decimal
#   - recommended_rate_ceiling: Decimal
#   - reasoning: str
#   - status: str
#
# USDStrategyConfigCreate
#   - target_usd_balance: Decimal
#   - risk_tolerance: str ("conservative" | "moderate" | "aggressive")
#   - max_single_purchase_pct: Decimal (0-100)
#   - preferred_rate_percentile: Decimal (0-100)
#   - lookback_days: int (30-365)
#
# USDStrategyConfigRead
#   - All fields from USDStrategyConfigCreate plus:
#   - current_usd_balance: Decimal
#   - updated_by: UUID
#   - updated_at: datetime
#
# USDStrategyPerformance
#   - period: str
#   - strategy_avg_rate: Decimal (weighted average rate achieved)
#   - naive_avg_rate: Decimal (simple average market rate over same period)
#   - savings_pct: float (% saved vs naive approach)
#   - total_usd_purchased: Decimal
#   - total_ngn_spent: Decimal
#
# USDSimulationRequest
#   - risk_tolerance: str
#   - lookback_days: int
#   - simulation_start_date: date
#   - simulation_end_date: date
#
# USDSimulationResult
#   - strategy_avg_rate: Decimal
#   - naive_avg_rate: Decimal
#   - savings_pct: float
#   - purchase_events: list[dict] (date, amount_usd, rate, reasoning)
#
# --- Reorder Suggestion Schemas ---
# ReorderSuggestionRead
#   - id: UUID
#   - product_id: UUID
#   - product_name: str
#   - current_stock: int
#   - reorder_point: int
#   - suggested_order_quantity: int
#   - economic_order_quantity: int
#   - safety_stock: int
#   - lead_time_days: int
#   - avg_daily_demand: Decimal
#   - estimated_stockout_date: date | None
#   - urgency: str ("critical" | "soon" | "planned")
#   - confidence: Decimal
#   - reasoning: str
#   - status: str
#   - created_at: datetime
#
# ReorderSuggestionListResponse
#   - items: list[ReorderSuggestionRead]
#   - total: int
#   - critical_count: int
#
# ReorderConfigRead
#   - default_lead_time_days: int
#   - safety_stock_multiplier: Decimal
#   - service_level_target: Decimal
#   - demand_lookback_days: int
#   - holding_cost_pct: Decimal
#   - updated_at: datetime
#
# ReorderConfigUpdate
#   - All fields optional
#   - default_lead_time_days: int | None
#   - safety_stock_multiplier: Decimal | None
#   - service_level_target: Decimal | None
#   - demand_lookback_days: int | None
#   - holding_cost_pct: Decimal | None
#
# ReorderPerformance
#   - total_suggestions: int
#   - approved_count: int
#   - predicted_stockouts: int
#   - actual_stockouts: int
#   - accuracy_pct: float
#   - avg_lead_time_accuracy_days: float (predicted vs actual lead time)
