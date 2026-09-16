"""Billing domain exceptions."""


class InvalidTierError(Exception):
    """Raised when an unrecognized subscription tier is requested."""

    def __init__(self, tier: str):
        self.tier = tier
        super().__init__(f"Invalid subscription tier: {tier}")


class BillingNotConfiguredError(Exception):
    """Raised when Paystack credentials or Plan codes aren't set yet."""

    def __init__(self, detail: str):
        super().__init__(detail)


class BusinessNotFoundError(Exception):
    """Raised when the given business_id doesn't exist."""

    def __init__(self, business_id):
        self.business_id = business_id
        super().__init__(f"Business not found: {business_id}")


class BusinessOwnerNotFoundError(Exception):
    """Raised when a business has no OWNER-role user -- shouldn't happen in
    practice (onboarding always creates one), but checkout needs a real
    email to create the Paystack customer against, so fail clearly rather
    than silently using a wrong/missing address."""

    def __init__(self, business_id):
        self.business_id = business_id
        super().__init__(f"No owner user found for business: {business_id}")


class PaystackAPIError(Exception):
    """Raised when a Paystack API call fails (non-2xx response or network error)."""

    def __init__(self, detail: str):
        super().__init__(detail)
