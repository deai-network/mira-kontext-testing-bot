"""Custom exceptions for the testing bot."""


class BotError(Exception):
    """Base exception for bot errors."""

    pass


class ConfigurationError(BotError):
    """Raised when configuration is missing or invalid."""

    pass


class KontextAPIError(BotError):
    """Raised when the Kontext API returns an error."""

    pass


class AuthenticationError(KontextAPIError):
    """Raised when authentication fails."""

    pass


class PermissionError(KontextAPIError):
    """Raised when a permission check fails."""

    pass


class NotFoundError(KontextAPIError):
    """Raised when a requested resource is not found."""

    pass


class ValidationError(KontextAPIError):
    """Raised when request validation fails."""

    pass


class SourceIsolationError(KontextAPIError):
    """Raised when the API cannot safely enforce source isolation."""

    pass
