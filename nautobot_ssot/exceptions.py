"""Custom Exceptions to be used with SSoT integrations."""


class AdapterLoadException(Exception):
    """Raised when there's an error while loading data."""


class AuthFailure(Exception):
    """Exception raised when authenticating to endpoint fails."""

    def __init__(self, error_code, message):
        """Populate exception information."""
        self.expression = error_code
        self.message = message
        super().__init__(self.message)


class ConfigurationError(Exception):
    """Exception thrown when Job configuration is wrong."""


class JobException(Exception):
    """Exception raised when failure loading integration Job."""

    def __init__(self, message):
        """Populate exception information."""
        self.message = message
        super().__init__(self.message)


class InvalidUrlScheme(Exception):
    """Exception raised for wrong scheme being passed for URL.

    Attributes:
        message (str): Returned explanation of Error.
    """

    def __init__(self, scheme):
        """Initialize Exception with wrong scheme in message."""
        self.message = f"Invalid URL scheme '{scheme}' found!"
        super().__init__(self.message)


class MissingConfigSetting(Exception):
    """Exception raised for missing configuration settings.

    Attributes:
        message (str): Returned explanation of Error.
    """

    def __init__(self, setting):
        """Initialize Exception with Setting that is missing and message."""
        self.setting = setting
        self.message = f"Missing configuration setting - {setting}!"
        super().__init__(self.message)


class MissingSecretsGroupException(Exception):
    """Custom Exception in case SecretsGroup is not found on ExternalIntegration."""


class RequestConnectError(Exception):
    """Exception class to be raised upon requests module connection errors."""


class RequestHTTPError(Exception):
    """Exception class to be raised upon requests module HTTP errors."""
