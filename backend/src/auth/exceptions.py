"""Auth domain exceptions."""


class InvalidCredentialsError(Exception):
    """Raised when email/password combination is invalid."""


class AccountLockedError(Exception):
    """Raised when user account is locked due to failed login attempts."""

    def __init__(self, locked_until):
        self.locked_until = locked_until
        super().__init__(f"Account locked until {locked_until}")


class UserAlreadyExistsError(Exception):
    """Raised when attempting to register with an existing email."""


class WeakPasswordError(Exception):
    """Raised when password does not meet complexity requirements."""
