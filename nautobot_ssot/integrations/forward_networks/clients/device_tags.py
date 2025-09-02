"""Forward Networks Device Tags API module."""

from typing import Any, Dict, List

from .base import BaseResource


class DeviceTagsAPI(BaseResource):
    """Forward Networks Device Tags API resource."""

    def get_device_tags(self, network_id: str) -> List[Dict[str, Any]]:
        """GET /api/networks/{networkId}/device-tags - Get all device tags."""
        resp = self._client.get(f"/api/networks/{network_id}/device-tags")
        return self._handle_response(resp)

    def create_device_tag(self, network_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/networks/{networkId}/device-tags - Create a device tag."""
        resp = self._client.post(f"/api/networks/{network_id}/device-tags", json=data)
        return self._handle_response(resp)
