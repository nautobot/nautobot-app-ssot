"""Forward Enterprise API client utilities."""

import logging
import re
from typing import Any, Dict, Optional

import requests
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices

from nautobot_ssot.integrations.forward_enterprise import constants
from nautobot_ssot.integrations.forward_enterprise.exceptions import (
    ForwardEnterpriseAPIError,
    ForwardEnterpriseAuthenticationError,
    ForwardEnterpriseConnectionError,
    ForwardEnterpriseQueryError,
    ForwardEnterpriseValidationError,
)

logger = logging.getLogger(__name__)


class ForwardEnterpriseClient:
    """Client for communicating with Forward Enterprise API."""

    def __init__(self, job, verify_ssl: bool = True, **kwargs):
        """Initialize the Forward Enterprise client.

        Args:
            job: The Nautobot job instance with credentials configuration (required)
            verify_ssl (bool): Whether to verify SSL certificates
            **kwargs: Additional keyword arguments (for future extensibility)
        """
        if not job or not hasattr(job, "credentials"):
            raise ForwardEnterpriseValidationError("Job with credentials is required")

        self.job = job
        self.verify_ssl = verify_ssl

        # Get API URL from External Integration
        self.api_url = job.credentials.remote_url.rstrip("/")

        # Securely retrieve API token from External Integration's secrets group
        self.api_token = job.credentials.secrets_group.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
        )

    def _is_query_id(self, text: str) -> bool:
        """Check if a text string looks like a query ID.

        Query IDs typically start with 'Q_' followed by alphanumeric characters and underscores.

        Args:
            text (str): The text to check

        Returns:
            bool: True if the text looks like a query ID, False otherwise
        """
        if not text:
            return False
        return text.startswith("Q_") and bool(re.match(constants.QUERY_ID_PATTERN, text))

    def validate_query_parameters(self, query: Optional[str] = None, query_id: Optional[str] = None):
        """Validate that query and query_id parameters are used correctly.

        Args:
            query (str, optional): The NQE query source code
            query_id (str, optional): The Query ID from NQE Library

        Raises:
            ForwardEnterpriseValidationError: If validation fails
        """
        if not query and not query_id:
            raise ForwardEnterpriseValidationError("Either query or query_id must be provided")

        if query and query_id:
            raise ForwardEnterpriseValidationError("Cannot specify both query and query_id")

        if query and self._is_query_id(query):
            logger.warning(
                "Query parameter '%s' looks like a query ID (starts with 'Q_'). "
                "Consider using query_id parameter instead.",
                query,
            )

        if query_id and not self._is_query_id(query_id):
            logger.warning(
                "Query ID parameter '%s' doesn't look like a query ID "
                "(should start with 'Q_'). Consider using query parameter instead.",
                query_id,
            )

    def _clean_query(self, query: str) -> str:
        """Clean up a query by removing comments and normalizing whitespace.

        Args:
            query (str): The raw query string

        Returns:
            str: The cleaned query string
        """
        # Clean up the query: strip whitespace and remove NQE comments
        cleaned_query = query.strip()
        # Remove NQE comments (// comments)
        lines = cleaned_query.split("\n")
        cleaned_lines = []
        for line in lines:
            # Remove // comments but preserve the rest of the line
            comment_index = line.find("//")
            if comment_index != -1:
                line = line[:comment_index]
            # Keep non-empty lines
            if line.strip():
                cleaned_lines.append(line.strip())

        # Join with spaces and normalize whitespace
        cleaned_query = " ".join(cleaned_lines)
        cleaned_query = re.sub(r"\s+", " ", cleaned_query)
        return cleaned_query

    # pylint: disable=too-many-arguments, too-many-branches, too-many-locals, too-many-statements
    def execute_nqe_query(
        self,
        query: Optional[str] = None,
        network_id: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        query_id: Optional[str] = None,
        commit_id: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        *,
        max_items: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> list:
        """Execute an NQE query against Forward Enterprise.

        Args:
            query (str, optional): The NQE query source code to execute
            network_id (str, optional): The network ID to query against
            snapshot_id (str, optional): The snapshot ID to query against
            query_id (str, optional): The Query ID from NQE Library to execute
            commit_id (str, optional): Specific version of the query to run
            parameters (dict, optional): Parameters for the query
            max_items (int, optional): Maximum number of items to return (useful to cap responses)
            page_size (int, optional): Page size for paginated requests (defaults to Forward constant)

        Returns:
            list: The query results

        Raises:
            ForwardEnterpriseValidationError: If neither query nor query_id is provided
            ForwardEnterpriseAuthenticationError: If authentication fails
            ForwardEnterpriseAPIError: If the API request fails
            ForwardEnterpriseConnectionError: If connection fails
            ForwardEnterpriseQueryError: If query execution fails
        """
        # Validate query parameters
        self.validate_query_parameters(query, query_id)

        url = self.api_url  # Use the full URL as provided by External Integration

        # Build query parameters
        params = {}
        if network_id:
            params["networkId"] = network_id
        if snapshot_id:
            params["snapshotId"] = snapshot_id

        # Build request payload - either query source or queryId is required
        base_payload: Dict[str, Any] = {}
        if query:
            cleaned_query = self._clean_query(query)
            base_payload["query"] = cleaned_query
        elif query_id:
            base_payload["queryId"] = query_id
            if commit_id:
                base_payload["commitId"] = commit_id
        else:
            raise ForwardEnterpriseValidationError("Either 'query' or 'query_id' must be provided")

        if parameters:
            base_payload["parameters"] = parameters

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Basic {self.api_token}",
        }

        effective_page_size = page_size or constants.DEFAULT_PAGE_SIZE
        collected: list = []
        offset = 0
        total_num_items: Optional[int] = None

        try:
            while True:
                payload = dict(base_payload)
                payload["queryOptions"] = {"offset": offset, "limit": effective_page_size}

                if self.job:
                    self.job.logger.info("Forward Enterprise request URL: %s", url)
                    self.job.logger.info("Forward Enterprise request payload: %s", payload)

                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    params=params,
                    timeout=constants.DEFAULT_API_TIMEOUT,
                    verify=self.verify_ssl,
                )

                # Handle specific HTTP status codes
                if response.status_code == 401:
                    raise ForwardEnterpriseAuthenticationError(
                        "Authentication failed. Check API token and permissions."
                    )
                if response.status_code == 403:
                    raise ForwardEnterpriseAuthenticationError(
                        "Access denied. Insufficient permissions for this operation."
                    )
                if response.status_code == 400:
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("message", "Bad request")
                    except (ValueError, KeyError):
                        error_msg = response.text or "Bad request"
                    raise ForwardEnterpriseQueryError(
                        f"Query validation failed: {error_msg}", query=query, query_id=query_id
                    )
                if not response.ok:
                    raise ForwardEnterpriseAPIError(
                        f"API request failed with status {response.status_code}: {response.text}",
                        status_code=response.status_code,
                        response_content=response.text,
                    )

                try:
                    data = response.json()
                except ValueError as error_data:
                    raise ForwardEnterpriseAPIError(
                        f"Invalid JSON response from API: {error_data}", response_content=response.text
                    ) from error_data

                # Handle API-level errors in response
                if isinstance(data, dict) and data.get("error"):
                    error_msg = data.get("error", {}).get("message", "Unknown API error")
                    raise ForwardEnterpriseQueryError(
                        f"Query execution failed: {error_msg}", query=query, query_id=query_id
                    )

                if isinstance(data, dict):
                    items = data.get("items", []) or []
                    total_num_items = data.get("totalNumItems", total_num_items)
                elif isinstance(data, list):
                    items = data
                    total_num_items = None
                else:
                    if self.job:
                        self.job.logger.warning("Unexpected response format: %s", type(data))
                    items = []

                collected.extend(items)

                if max_items is not None and len(collected) >= max_items:
                    collected = collected[:max_items]
                    break

                if len(items) < effective_page_size:
                    break

                if total_num_items is not None and (offset + len(items)) >= total_num_items:
                    break

                offset += len(items)

            if self.job:
                self.job.logger.info("Forward Enterprise response: %s items returned", len(collected))

            return collected

        except requests.exceptions.ConnectionError as exception:
            error_msg = f"Connection failed to Forward Enterprise: {exception}"
            if self.job:
                self.job.logger.error(error_msg)
            raise ForwardEnterpriseConnectionError(error_msg) from exception
        except requests.exceptions.Timeout as exception:
            error_msg = f"Request timeout to Forward Enterprise: {exception}"
            if self.job:
                self.job.logger.error(error_msg)
            raise ForwardEnterpriseConnectionError(error_msg) from exception
        except requests.exceptions.RequestException as exception:
            error_msg = f"HTTP request failed: {exception}"
            if self.job:
                self.job.logger.error(error_msg)
            raise ForwardEnterpriseAPIError(error_msg) from exception

    # Query configuration mappings
    QUERY_MAPPINGS = {
        "device": ["device_query"],
        "interface": ["interface_query"],
        "ipam": ["ipam_query"],
    }

    # Query ID mappings for saved queries
    QUERY_ID_MAPPINGS = {
        "device": ["device_query_id"],
        "interface": ["interface_query_id"],
        "ipam": ["ipam_query_id"],
    }

    def get_query_from_config(self, query_type: str) -> Optional[str]:
        """Get query from job's extra_config.

        Args:
            query_type (str): Type of query ('device', 'interface', 'ipam')

        Returns:
            str or None: The query from configuration, or None if not found
        """
        if not (self.job and hasattr(self.job, "credentials") and hasattr(self.job.credentials, "extra_config")):
            return None

        extra_config = self.job.credentials.extra_config or {}

        # Get the query for the specified type
        for key in self.QUERY_MAPPINGS.get(query_type, []):
            if query := extra_config.get(key):
                return query
        return None

    def get_query_id_from_config(self, query_type: str) -> Optional[str]:
        """Get query ID from job's extra_config.

        Args:
            query_type (str): Type of query ('device', 'interface', 'ipam')

        Returns:
            str or None: The query ID from configuration, or None if not found
        """
        if not (self.job and hasattr(self.job, "credentials") and hasattr(self.job.credentials, "extra_config")):
            return None

        extra_config = self.job.credentials.extra_config or {}

        # Get the query ID for the specified type
        for key in self.QUERY_ID_MAPPINGS.get(query_type, []):
            if query_id := extra_config.get(key):
                return query_id
        return None

    def get_device_query_from_config(self) -> Optional[str]:
        """Get device query from job's extra_config."""
        return self.get_query_from_config("device")

    def get_interface_query_from_config(self) -> Optional[str]:
        """Get interface query from job's extra_config."""
        return self.get_query_from_config("interface")

    def get_ipam_query_from_config(self) -> Optional[str]:
        """Get IPAM query from job's extra_config."""
        return self.get_query_from_config("ipam")

    def get_device_query_id_from_config(self) -> Optional[str]:
        """Get device query ID from job's extra_config."""
        return self.get_query_id_from_config("device")

    def get_interface_query_id_from_config(self) -> Optional[str]:
        """Get interface query ID from job's extra_config."""
        return self.get_query_id_from_config("interface")

    def get_ipam_query_id_from_config(self) -> Optional[str]:
        """Get IPAM query ID from job's extra_config."""
        return self.get_query_id_from_config("ipam")
