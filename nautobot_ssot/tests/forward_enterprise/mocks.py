"""Mock classes for Forward Enterprise NQE API testing."""

from typing import Any, Dict, Optional

from .fixtures import NQE_QUERY_MAPPINGS


class MockNQEAPI:
    """Mock NQEAPI for testing Forward Enterprise integration."""

    def __init__(self):
        """Initialize mock NQE API."""
        self.query_mappings = NQE_QUERY_MAPPINGS.copy()

    def run_query(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mock NQE query execution based on query content."""
        query = data.get("query", "").lower()

        # Match query content to return appropriate mock data
        if "interface" in query:
            return self.query_mappings["interface_query"]
        if "device" in query:
            return self.query_mappings["device_query"]
        if "ipam" in query or "ip" in query:
            return self.query_mappings["ipam_query"]
        else:
            # Default empty response for unknown queries
            return {"snapshotId": data.get("snapshotId", "393879"), "items": []}


class MockForwardEnterpriseClient:
    """Mock Forward Enterprise client focused on NQE functionality."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        verify_ssl: bool = True,
        job=None,
        **kwargs,
    ):  # pylint disable=too-many-arguments, too-many-positional-arguments
        """Initialize mock client."""
        self.base_url = base_url or "https://test.example.com"
        self.username = username or "test_user"
        self.password = password or "test_token"
        self.verify_ssl = verify_ssl
        self.job = job
        self.nqe = MockNQEAPI()

    def get_device_query_from_config(self) -> str:
        """Mock method to return device query."""
        return "mock_device_query"

    def get_interface_query_from_config(self) -> str:
        """Mock method to return interface query."""
        return "mock_interface_query"

    def get_ipam_query_from_config(self) -> str:
        """Mock method to return IPAM query."""
        return "mock_ipam_query"

    def get_device_query_id_from_config(self) -> str:
        """Mock method to return device query ID."""
        return "Q_mock_device_123"

    def get_interface_query_id_from_config(self) -> str:
        """Mock method to return interface query ID."""
        return "Q_mock_interface_456"

    def get_ipam_query_id_from_config(self) -> str:
        """Mock method to return IPAM query ID."""
        return "Q_mock_ipam_789"

    def execute_nqe_query(self, query: Optional[str] = None, query_id: Optional[str] = None, **kwargs) -> list:
        """Mock execute_nqe_query method that uses the MockNQEAPI."""
        # Create data dict for the nqe.run_query method
        data = {}
        if query:
            data["query"] = query
        if query_id:
            data["queryId"] = query_id

        # Get the result from MockNQEAPI
        result = self.nqe.run_query(data)

        # Return the items array, which is what execute_nqe_query returns
        return result.get("items", [])

    def close(self):
        """Mock close method."""

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
