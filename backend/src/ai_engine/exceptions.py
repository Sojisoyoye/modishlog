# TODO: Domain-specific exceptions for the AI Engine domain
#
# RecommendationNotFoundError(Exception)
#   - Raised when a recommendation lookup by ID yields no result.
#   - Attributes: recommendation_id
#
# RecommendationExpiredError(Exception)
#   - Raised when attempting to accept a recommendation that has expired.
#   - Attributes: recommendation_id, expired_at
#
# RecommendationAlreadyProcessedError(Exception)
#   - Raised when attempting to accept/dismiss a recommendation that is not in "pending" status.
#   - Attributes: recommendation_id, current_status
#
# RecommendationExecutionError(Exception)
#   - Raised when applying a recommendation's action_payload fails in the target domain service.
#   - Attributes: recommendation_id, action_type, error_detail
#
# USDStrategyConfigNotFoundError(Exception)
#   - Raised when no USD strategy configuration exists.
#
# USDStrategyInsufficientDataError(Exception)
#   - Raised when there is not enough FX rate history to generate a USD purchase schedule.
#   - Attributes: available_days, required_days
#
# ReorderSuggestionNotFoundError(Exception)
#   - Raised when a reorder suggestion lookup yields no result.
#   - Attributes: product_id or suggestion_id
#
# ReorderConversionError(Exception)
#   - Raised when converting a reorder suggestion to a purchase order fails.
#   - Attributes: suggestion_id, error_detail
#
# InsufficientSalesDataError(Exception)
#   - Raised when there is not enough sales history to compute demand patterns for reorder suggestions.
#   - Attributes: product_id, available_days, required_days
#
# AIModelError(Exception)
#   - Raised when an underlying AI/ML model call fails (e.g. optimization, prediction).
#   - Attributes: model_name, error_detail
