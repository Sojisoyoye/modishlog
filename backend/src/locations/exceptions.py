"""Locations domain exceptions."""


class LocationNotFoundError(Exception):
    """Raised when a location lookup yields no result."""

    def __init__(self, location_id=None):
        self.location_id = location_id
        super().__init__(f"Location not found: {location_id}")


class DuplicateLocationCodeError(Exception):
    """Raised when a location code already exists."""

    def __init__(self, code=None):
        self.code = code
        super().__init__(f"Location code already exists: {code}")
