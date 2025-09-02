"""Forward Networks Network API module."""

from typing import Any, Dict, List

from .base import BaseResource


class NetworkAPI(BaseResource):
    """Forward Networks Network API resource."""

    def get_networks(self) -> List[Dict[str, Any]]:
        """GET /api/networks - Get all networks."""
        resp = self._client.get("/api/networks")
        return self._handle_response(resp)

    def create_network(self, name: str) -> Dict[str, Any]:
        """POST /api/networks - Create a network."""
        resp = self._client.post("/api/networks", params={"name": name})
        return self._handle_response(resp)

    def delete_network(self, network_id: str) -> None:
        """DELETE /api/networks/{networkId} - Delete a network."""
        resp = self._client.delete(f"/api/networks/{network_id}")
        return self._handle_response(resp)

    def update_network(self, network_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """PATCH /api/networks/{networkId} - Update a network."""
        resp = self._client.patch(f"/api/networks/{network_id}", json=data)
        return self._handle_response(resp)
