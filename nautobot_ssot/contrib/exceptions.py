"""Contrib module exceptions."""


class CachedObjectNotFound(Exception):
    """Exception for if an object is not found in the cache."""


class CachedObjectAlreadyExists(Exception):
    """Excpetion for if an object already exists in the cache when adding."""


class InvalidResponseWarning(BaseException):
    """Custom warning for use in `NautobotAdapter` class indicating an invalid response."""
