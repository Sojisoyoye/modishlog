# TODO: Domain-specific exceptions for the Pricing domain
#
# ElasticityNotFoundError(Exception)
#   - Raised when no elasticity analysis exists for a requested product.
#   - Attributes: product_id
#
# InsufficientPriceDataError(Exception)
#   - Raised when there are not enough historical price/sales data points to compute elasticity.
#   - Attributes: product_id, available_points, required_points
#
# MarginTargetNotFoundError(Exception)
#   - Raised when a margin target lookup yields no result.
#   - Attributes: product_id or category_id
#
# OptimizationInfeasibleError(Exception)
#   - Raised when the portfolio optimization problem has no feasible solution
#     (e.g. conflicting constraints make it impossible to meet all margin targets).
#   - Attributes: conflicting_constraints (list of descriptions)
#
# RecommendationNotFoundError(Exception)
#   - Raised when a pricing recommendation lookup by ID yields no result.
#   - Attributes: recommendation_id
#
# RecommendationExpiredError(Exception)
#   - Raised when attempting to apply a recommendation that is too old or conditions have changed.
#   - Attributes: recommendation_id, created_at, max_age_days
#
# CrossSubsidyAnalysisError(Exception)
#   - Raised when cross-subsidization analysis cannot be performed (e.g. too few products).
#   - Attributes: reason
