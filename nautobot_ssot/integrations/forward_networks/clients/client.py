"""Forward Networks API client module."""

import httpx

from .collection import CollectionAPI
from .device_tags import DeviceTagsAPI
from .devices import DevicesAPI
from .locations import LocationsAPI
from .networks import NetworkAPI
from .nqe import NQEAPI
from .snapshots import SnapshotsAPI


class ForwardNetworksClient:
    """Client for interacting with Forward Networks API."""

    def __init__(self, base_url: str, username: str, password: str, verify_ssl: bool = True):
        """Initialize the Forward Networks API client.

        Args:
            base_url: The base URL of the Forward Networks API
            username: Username for authentication
            password: Password for authentication
            verify_ssl: Whether to verify SSL certificates
        """
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            auth=(username, password),
            verify=verify_ssl,
            headers={"Accept": "application/json"},
        )
        self.networks = NetworkAPI(self._client)
        self.locations = LocationsAPI(self._client)
        self.devices = DevicesAPI(self._client)
        self.device_tags = DeviceTagsAPI(self._client)
        self.snapshots = SnapshotsAPI(self._client)
        self.collection = CollectionAPI(self._client)
        self.nqe = NQEAPI(self._client)

    def close(self):
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
