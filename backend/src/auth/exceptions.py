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


class InvalidResetTokenError(Exception):
    """Raised when a password-reset token is invalid, expired, or already used."""


class InvalidRefreshTokenError(Exception):
    """Raised when a refresh token is invalid, expired, or revoked."""


class UserNotFoundError(Exception):
    """Raised when a requested user account does not exist."""


class CannotModifySelfError(Exception):
    """Raised when an admin attempts a destructive action on their own account."""
