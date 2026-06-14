"""AI Engine domain exceptions."""

import uuid
from datetime import datetime


class RecommendationNotFoundError(Exception):
    """Raised when a recommendation lookup by ID yields no result."""

    def __init__(self, recommendation_id: uuid.UUID) -> None:
        self.recommendation_id = recommendation_id
        super().__init__(f"Recommendation {recommendation_id} not found")


class RecommendationExpiredError(Exception):
    """Raised when attempting to accept a recommendation that has expired."""

    def __init__(
        self,
        recommendation_id: uuid.UUID,
        expired_at: datetime,
    ) -> None:
        self.recommendation_id = recommendation_id
        self.expired_at = expired_at
        super().__init__(f"Recommendation {recommendation_id} expired at {expired_at}")


class RecommendationAlreadyProcessedError(Exception):
    """Raised when accepting/dismissing a non-pending recommendation."""

    def __init__(
        self,
        recommendation_id: uuid.UUID,
        current_status: str,
    ) -> None:
        self.recommendation_id = recommendation_id
        self.current_status = current_status
        super().__init__(f"Recommendation {recommendation_id} already {current_status}")


class USDStrategyConfigNotFoundError(Exception):
    """Raised when no USD strategy configuration exists."""

    def __init__(self) -> None:
        super().__init__("No USD strategy configuration found")


class ReorderSuggestionNotFoundError(Exception):
    """Raised when a reorder suggestion lookup yields no result."""

    def __init__(self, identifier: uuid.UUID) -> None:
        self.identifier = identifier
        super().__init__(f"Reorder suggestion not found: {identifier}")
