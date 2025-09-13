"""Forward Enterprise integration specific exceptions."""


class ForwardEnterpriseError(Exception):
    """Base exception for Forward Enterprise integration errors."""


class ForwardEnterpriseAPIError(ForwardEnterpriseError):
    """Exception raised for Forward Enterprise API errors."""

    def __init__(self, message, status_code=None, response_content=None):
        """Initialize the API error with additional context.

        Args:
            message (str): Error message
            status_code (int, optional): HTTP status code from API response
            response_content (str, optional): Raw API response content
        """
        super().__init__(message)
        self.status_code = status_code
        self.response_content = response_content


class ForwardEnterpriseConnectionError(ForwardEnterpriseError):
    """Exception raised for Forward Enterprise connection errors."""


class ForwardEnterpriseAuthenticationError(ForwardEnterpriseError):
    """Exception raised for Forward Enterprise authentication errors."""


class ForwardEnterpriseValidationError(ForwardEnterpriseError):
    """Exception raised for Forward Enterprise validation errors."""


class ForwardEnterpriseQueryError(ForwardEnterpriseError):
    """Exception raised for Forward Enterprise query errors."""

    def __init__(self, message, query=None, query_id=None):
        """Initialize the query error with query context.

        Args:
            message (str): Error message
            query (str, optional): The NQE query that failed
            query_id (str, optional): The query ID that failed
        """
        super().__init__(message)
        self.query = query
        self.query_id = query_id
