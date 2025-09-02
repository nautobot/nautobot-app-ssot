"""Forward Networks Devices API module."""

from typing import Any, Dict, List

from .base import BaseResource


class DevicesAPI(BaseResource):
    """Forward Networks Devices API resource."""

    def get_devices(self, network_id: str, **filters) -> List[Dict[str, Any]]:
        """GET /api/networks/{networkId}/devices - Get devices in a network."""
        params = {k: v for k, v in filters.items() if v is not None}
        resp = self._client.get(f"/api/networks/{network_id}/devices", params=params)
        return self._handle_response(resp)

    def get_device(self, network_id: str, device_name: str) -> Dict[str, Any]:
        """GET /api/networks/{networkId}/devices/{deviceName} - Get a specific device."""
        resp = self._client.get(f"/api/networks/{network_id}/devices/{device_name}")
        return self._handle_response(resp)
