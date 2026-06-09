"""Pricing domain exceptions."""


class ElasticityNotFoundError(Exception):
    """No elasticity analysis exists for a product."""

    def __init__(self, product_id):
        self.product_id = product_id
        super().__init__(f"No elasticity data for product {product_id}")


class InsufficientPriceDataError(Exception):
    """Not enough historical data to compute elasticity."""

    def __init__(self, product_id, available_points, required_points):
        self.product_id = product_id
        self.available_points = available_points
        self.required_points = required_points
        super().__init__(
            f"Product {product_id}: {available_points} data points "
            f"(need {required_points})"
        )


class MarginTargetNotFoundError(Exception):
    """Margin target lookup yielded no result."""

    def __init__(self, target_id):
        self.target_id = target_id
        super().__init__(f"Margin target {target_id} not found")


class OptimizationInfeasibleError(Exception):
    """Portfolio optimization has no feasible solution."""

    def __init__(self, reason="conflicting constraints"):
        self.reason = reason
        super().__init__(f"Optimization infeasible: {reason}")


class RecommendationNotFoundError(Exception):
    """Pricing recommendation lookup failed."""

    def __init__(self, recommendation_id):
        self.recommendation_id = recommendation_id
        super().__init__(f"Recommendation {recommendation_id} not found")


class RecommendationExpiredError(Exception):
    """Recommendation is too old to apply."""

    def __init__(self, recommendation_id, created_at, max_age_days):
        self.recommendation_id = recommendation_id
        self.created_at = created_at
        self.max_age_days = max_age_days
        super().__init__(
            f"Recommendation {recommendation_id} expired "
            f"(created {created_at}, max age {max_age_days}d)"
        )


class CrossSubsidyAnalysisError(Exception):
    """Cross-subsidization analysis cannot be performed."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(f"Cross-subsidy analysis error: {reason}")


class MixTargetSumError(Exception):
    """Product mix target percentages do not sum to 100."""

    def __init__(self, total):
        self.total = total
        super().__init__(f"Mix target percentages must sum to 100, got {total}")
