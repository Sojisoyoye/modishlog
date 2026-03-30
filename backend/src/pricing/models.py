# TODO: SQLAlchemy models for the Pricing domain
#
# DemandElasticity
#   - id: UUID primary key
#   - product_id: ForeignKey -> Product.id, unique
#   - elasticity_coefficient: Numeric(8, 4) - price elasticity of demand (PED)
#     (e.g. -1.5 means 1% price increase leads to 1.5% demand decrease)
#   - r_squared: Numeric(5, 4) - model fit quality (0 to 1)
#   - data_points_used: Integer - number of price/quantity observations
#   - calculation_date: Date
#   - price_range_min: Numeric(12, 2) - observed price range
#   - price_range_max: Numeric(12, 2)
#   - demand_curve_data: JSON (list of {price, estimated_demand} for charting)
#   - created_at: DateTime with timezone
#
# MarginTarget
#   - id: UUID primary key
#   - product_id: ForeignKey -> Product.id, nullable (null = category-level target)
#   - category_id: ForeignKey -> ProductCategory.id, nullable
#   - target_margin_pct: Numeric(5, 2) - desired gross margin percentage
#   - min_margin_pct: Numeric(5, 2) - minimum acceptable margin (floor)
#   - priority: Integer, default 1 (for optimization weighting)
#   - set_by: ForeignKey -> User.id
#   - created_at: DateTime with timezone
#   - updated_at: DateTime with timezone
#
# PricingRecommendation
#   - id: UUID primary key
#   - product_id: ForeignKey -> Product.id
#   - current_price: Numeric(12, 2)
#   - recommended_price: Numeric(12, 2)
#   - expected_demand_change_pct: Numeric(5, 2)
#   - expected_revenue_change_pct: Numeric(5, 2)
#   - expected_margin_change_pct: Numeric(5, 2)
#   - confidence: Numeric(5, 2) - confidence score (0 to 100)
#   - reasoning: Text - AI-generated explanation
#   - status: String ("pending", "applied", "rejected", "expired")
#   - applied_at: DateTime, nullable
#   - applied_by: ForeignKey -> User.id, nullable
#   - created_at: DateTime with timezone
#
# CrossSubsidyAnalysis
#   - id: UUID primary key
#   - analysis_date: Date
#   - portfolio_total_margin: Numeric(14, 2)
#   - subsidy_matrix: JSON (dict of product_id -> {subsidizes: [...], subsidized_by: [...]})
#   - high_margin_products: JSON (list of product_ids carrying the portfolio)
#   - low_margin_products: JSON (list of product_ids being subsidized)
#   - recommendations: JSON (list of {product_id, action, reasoning})
#   - created_at: DateTime with timezone
