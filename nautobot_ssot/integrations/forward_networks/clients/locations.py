"""Forward Networks Locations API module."""

from typing import Any, Dict, List

from .base import BaseResource


class LocationsAPI(BaseResource):
    """Forward Networks Locations API resource."""

    def get_locations(self, network_id: str) -> List[Dict[str, Any]]:
        """GET /api/networks/{networkId}/locations - Get locations in a network."""
        resp = self._client.get(f"/api/networks/{network_id}/locations")
        return self._handle_response(resp)

    def create_location(self, network_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/networks/{networkId}/locations - Create a location."""
        resp = self._client.post(f"/api/networks/{network_id}/locations", json=data)
        return self._handle_response(resp)

    def update_location(self, network_id: str, location_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """PATCH /api/networks/{networkId}/locations/{locationId} - Update a location."""
        resp = self._client.patch(f"/api/networks/{network_id}/locations/{location_id}", json=data)
        return self._handle_response(resp)

    def delete_location(self, network_id: str, location_id: str) -> None:
        """DELETE /api/networks/{networkId}/locations/{locationId} - Delete a location."""
        resp = self._client.delete(f"/api/networks/{network_id}/locations/{location_id}")
        return self._handle_response(resp)
