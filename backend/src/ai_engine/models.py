# TODO: SQLAlchemy models for the AI Engine domain
#
# AIRecommendation
#   - id: UUID primary key
#   - category: String ("pricing", "inventory", "fx", "cashflow", "orders")
#   - title: String - short human-readable title
#   - description: Text - detailed AI-generated explanation
#   - priority: String ("high", "medium", "low")
#   - confidence: Numeric(5, 2) - confidence score (0 to 100)
#   - expected_impact: JSON ({metric: str, current_value, projected_value, change_pct})
#   - action_type: String ("price_change", "reorder", "fx_lock", "cost_cut", "usd_purchase")
#   - action_payload: JSON (structured data for executing the recommendation)
#   - reference_id: UUID, nullable (product_id, order_id, etc.)
#   - reference_type: String, nullable
#   - status: String ("pending", "accepted", "dismissed", "expired", "applied")
#   - dismissed_reason: Text, nullable
#   - accepted_by: ForeignKey -> User.id, nullable
#   - accepted_at: DateTime, nullable
#   - measured_outcome: JSON, nullable ({metric, actual_value, expected_value, accuracy_pct})
#   - created_at: DateTime with timezone
#   - expires_at: DateTime with timezone
#
# USDStrategyConfig
#   - id: UUID primary key
#   - target_usd_balance: Numeric(14, 2) - desired USD reserve
#   - current_usd_balance: Numeric(14, 2)
#   - risk_tolerance: String ("conservative", "moderate", "aggressive")
#   - max_single_purchase_pct: Numeric(5, 2) - max % of target to buy in one transaction
#   - preferred_rate_percentile: Numeric(5, 2) - buy when rate is below this percentile (e.g. 30th)
#   - lookback_days: Integer - historical window for rate analysis (e.g. 90)
#   - updated_by: ForeignKey -> User.id
#   - updated_at: DateTime with timezone
#
# USDPurchaseSchedule
#   - id: UUID primary key
#   - strategy_config_id: ForeignKey -> USDStrategyConfig.id
#   - recommended_date: Date
#   - recommended_amount_usd: Numeric(14, 2)
#   - recommended_rate_ceiling: Numeric(14, 4) - buy only if rate is at or below this
#   - reasoning: Text
#   - status: String ("upcoming", "executed", "skipped", "expired")
#   - executed_rate: Numeric(14, 4), nullable
#   - executed_amount_usd: Numeric(14, 2), nullable
#   - executed_at: DateTime, nullable
#   - created_at: DateTime with timezone
#
# ReorderSuggestion
#   - id: UUID primary key
#   - product_id: ForeignKey -> Product.id
#   - current_stock: Integer
#   - reorder_point: Integer - stock level that triggers reorder
#   - suggested_order_quantity: Integer
#   - economic_order_quantity: Integer - EOQ based on demand and holding cost
#   - safety_stock: Integer
#   - lead_time_days: Integer - expected supplier lead time
#   - avg_daily_demand: Numeric(8, 2)
#   - demand_variability: Numeric(8, 4) - coefficient of variation
#   - estimated_stockout_date: Date, nullable
#   - confidence: Numeric(5, 2)
#   - reasoning: Text
#   - status: String ("pending", "approved", "dismissed", "converted_to_order")
#   - converted_order_id: ForeignKey -> PurchaseOrder.id, nullable
#   - created_at: DateTime with timezone
#
# ReorderConfig
#   - id: UUID primary key
#   - default_lead_time_days: Integer, default 30
#   - safety_stock_multiplier: Numeric(4, 2), default 1.50 (1.5x standard deviation)
#   - service_level_target: Numeric(5, 2), default 95.00 (95% fill rate)
#   - demand_lookback_days: Integer, default 90
#   - holding_cost_pct: Numeric(5, 2) - annual holding cost as % of product cost
#   - updated_by: ForeignKey -> User.id
#   - updated_at: DateTime with timezone
