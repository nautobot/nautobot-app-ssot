"""Forward Networks Base Resource."""

from typing import Any

import httpx


class BaseResource:
    """Base class for Forward Networks API resources."""

    def __init__(self, client: httpx.Client):
        """Initialize the resource with an HTTP client."""
        self._client = client

    def _handle_response(self, response: httpx.Response) -> Any:
        """Handle the HTTP response."""
        response.raise_for_status()
        if response.status_code != 204:
            return response.json()
        return None
