"""Forward Networks Snapshots API client."""

from typing import Any, Dict, List

from .base import BaseResource


class SnapshotsAPI(BaseResource):
    """Forward Networks Snapshots API resource."""

    def get_snapshot(self, snapshot_id: str) -> Dict[str, Any]:
        """GET /api/snapshots/{snapshotId} - Get snapshot details."""
        resp = self._client.get(f"/api/snapshots/{snapshot_id}")
        return self._handle_response(resp)

    def delete_snapshot(self, snapshot_id: str) -> None:
        """DELETE /api/snapshots/{snapshotId} - Delete a snapshot."""
        resp = self._client.delete(f"/api/snapshots/{snapshot_id}")
        return self._handle_response(resp)

    def get_snapshot_devices(self, snapshot_id: str, device_name: str) -> Dict[str, Any]:
        """GET /api/snapshots/{snapshotId}/devices/{deviceName} - Get device from snapshot."""
        resp = self._client.get(f"/api/snapshots/{snapshot_id}/devices/{device_name}")
        return self._handle_response(resp)

    def get_snapshot_topology(self, snapshot_id: str, **params) -> Dict[str, Any]:
        """GET /api/snapshots/{snapshotId}/topology - Get snapshot topology."""
        resp = self._client.get(f"/api/snapshots/{snapshot_id}/topology", params=params)
        return self._handle_response(resp)

    def get_snapshot_metrics(self, snapshot_id: str) -> Dict[str, Any]:
        """GET /api/snapshots/{snapshotId}/metrics - Get snapshot metrics."""
        resp = self._client.get(f"/api/snapshots/{snapshot_id}/metrics")
        return self._handle_response(resp)

    def get_snapshot_vulnerabilities(self, snapshot_id: str, **params) -> List[Dict[str, Any]]:
        """GET /api/snapshots/{snapshotId}/vulnerabilities - Get vulnerabilities."""
        resp = self._client.get(f"/api/snapshots/{snapshot_id}/vulnerabilities", params=params)
        return self._handle_response(resp)

    def get_snapshots(self, network_id: str) -> List[Dict[str, Any]]:
        """GET /api/networks/{networkId}/snapshots - Get network snapshots."""
        resp = self._client.get(f"/api/networks/{network_id}/snapshots")
        return self._handle_response(resp)

    def get_latest_snapshot(self, network_id: str) -> Dict[str, Any]:
        """GET /api/networks/{networkId}/snapshots/latestProcessed - Get latest processed snapshot."""
        resp = self._client.get(f"/api/networks/{network_id}/snapshots/latestProcessed")
        return self._handle_response(resp)
