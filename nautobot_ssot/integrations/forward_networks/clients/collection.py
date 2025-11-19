"""Forward Networks Collection API module."""

from typing import Any, Dict, Optional

from .base import BaseResource


class CollectionAPI(BaseResource):
    """Forward Networks Collection API resource."""

    def start_collection(self, network_id: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """POST /api/networks/{networkId}/startcollection - Start network collection."""
        resp = self._client.post(f"/api/networks/{network_id}/startcollection", json=data or {})
        return self._handle_response(resp)

    def cancel_collection(self, network_id: str) -> Dict[str, Any]:
        """POST /api/networks/{networkId}/cancelcollection - Cancel network collection."""
        resp = self._client.post(f"/api/networks/{network_id}/cancelcollection")
        return self._handle_response(resp)
