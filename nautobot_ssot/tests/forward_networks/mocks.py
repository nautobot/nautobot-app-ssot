"""Mock classes for Forward Networks API testing."""

from typing import Any, Dict, List, Optional

from .fixtures import (
    MOCK_DEVICE_TAGS,
    MOCK_DEVICES,
    MOCK_LOCATIONS,
    MOCK_METRICS,
    MOCK_NETWORKS,
    MOCK_NQE_IP_QUERY_RESULT,
    MOCK_NQE_VLAN_QUERY_RESULT,
    MOCK_SNAPSHOTS,
    MOCK_TOPOLOGY,
    MOCK_VULNERABILITIES,
)


class MockLocationsAPI:
    """Mock LocationsAPI for testing."""

    def __init__(self):
        """Initialize mock API."""
        self.locations = MOCK_LOCATIONS.copy()

    def get_locations(self, network_id: str) -> List[Dict[str, Any]]:
        """Mock GET /api/networks/{networkId}/locations."""
        return self.locations

    def create_location(self, network_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mock POST /api/networks/{networkId}/locations."""
        new_location = {"id": f"location-{len(self.locations) + 1}", **data}
        self.locations.append(new_location)
        return new_location

    def update_location(self, network_id: str, location_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mock PATCH /api/networks/{networkId}/locations/{locationId}."""
        for location in self.locations:
            if location["id"] == location_id:
                location.update(data)
                return location
        raise ValueError(f"Location {location_id} not found")

    def delete_location(self, network_id: str, location_id: str) -> None:
        """Mock DELETE /api/networks/{networkId}/locations/{locationId}."""
        self.locations = [loc for loc in self.locations if loc["id"] != location_id]


class MockDevicesAPI:
    """Mock DevicesAPI for testing."""

    def __init__(self):
        """Initialize mock API."""
        self.devices = MOCK_DEVICES.copy()

    def get_devices(self, network_id: str, **filters) -> List[Dict[str, Any]]:
        """Mock GET /api/networks/{networkId}/devices."""
        # Filter devices by network if needed
        return self.devices

    def get_device(self, network_id: str, device_name: str) -> Dict[str, Any]:
        """Mock GET /api/networks/{networkId}/devices/{deviceName}."""
        for device in self.devices:
            if device["name"] == device_name:
                return device
        raise ValueError(f"Device {device_name} not found")


class MockDeviceTagsAPI:
    """Mock DeviceTagsAPI for testing."""

    def __init__(self):
        """Initialize mock API."""
        self.device_tags = MOCK_DEVICE_TAGS.copy()

    def get_device_tags(self, network_id: str) -> List[Dict[str, Any]]:
        """Mock GET /api/networks/{networkId}/device-tags."""
        return self.device_tags

    def create_device_tag(self, network_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mock POST /api/networks/{networkId}/device-tags."""
        new_tag = {"id": f"tag-{len(self.device_tags) + 1}", **data}
        self.device_tags.append(new_tag)
        return new_tag


class MockCollectionAPI:
    """Mock CollectionAPI for testing."""

    def start_collection(self, network_id: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Mock POST /api/networks/{networkId}/startcollection."""
        return {
            "status": "started",
            "collectionId": "collection-123",
            "networkId": network_id,
            "startTime": "2024-01-15T12:00:00Z",
        }

    def cancel_collection(self, network_id: str) -> Dict[str, Any]:
        """Mock POST /api/networks/{networkId}/cancelcollection."""
        return {"status": "cancelled", "networkId": network_id, "cancelTime": "2024-01-15T12:05:00Z"}


class MockNetworkAPI:
    """Mock NetworkAPI for testing."""

    def __init__(self):
        """Initialize mock API."""
        self.networks = MOCK_NETWORKS.copy()

    def get_networks(self) -> List[Dict[str, Any]]:
        """Mock GET /api/networks."""
        return self.networks

    def create_network(self, name: str) -> Dict[str, Any]:
        """Mock POST /api/networks."""
        new_network = {
            "id": f"network-{len(self.networks) + 1}",
            "name": name,
            "description": f"Network created via API: {name}",
            "status": "active",
            "created": "2024-01-15T12:00:00Z",
            "updated": "2024-01-15T12:00:00Z",
        }
        self.networks.append(new_network)
        return new_network

    def delete_network(self, network_id: str) -> None:
        """Mock DELETE /api/networks/{networkId}."""
        self.networks = [n for n in self.networks if n["id"] != network_id]

    def update_network(self, network_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mock PATCH /api/networks/{networkId}."""
        for network in self.networks:
            if network["id"] == network_id:
                network.update(data)
                network["updated"] = "2024-01-15T12:00:00Z"
                return network
        raise ValueError(f"Network {network_id} not found")


class MockSnapshotsAPI:
    """Mock SnapshotsAPI for testing."""

    def __init__(self):
        """Initialize mock API."""
        self.snapshots = MOCK_SNAPSHOTS.copy()

    def get_snapshots(self, network_id: str) -> List[Dict[str, Any]]:
        """Mock GET /api/networks/{networkId}/snapshots."""
        return [s for s in self.snapshots if s["networkId"] == network_id]

    def get_latest_snapshot(self, network_id: str) -> Dict[str, Any]:
        """Mock GET /api/networks/{networkId}/snapshots/latestProcessed."""
        for snapshot in self.snapshots:
            if snapshot["networkId"] == network_id and snapshot["isLatest"]:
                return snapshot
        raise ValueError(f"No latest snapshot found for network {network_id}")

    def get_snapshot(self, snapshot_id: str) -> Dict[str, Any]:
        """Mock GET /api/snapshots/{snapshotId}."""
        for snapshot in self.snapshots:
            if snapshot["id"] == snapshot_id:
                return snapshot
        raise ValueError(f"Snapshot {snapshot_id} not found")

    def delete_snapshot(self, snapshot_id: str) -> None:
        """Mock DELETE /api/snapshots/{snapshotId}."""
        self.snapshots = [s for s in self.snapshots if s["id"] != snapshot_id]

    def get_snapshot_devices(self, snapshot_id: str, device_name: str) -> Dict[str, Any]:
        """Mock GET /api/snapshots/{snapshotId}/devices/{deviceName}."""
        # Return device data from the specific snapshot
        for device in MOCK_DEVICES:
            if device["name"] == device_name:
                return {**device, "snapshotId": snapshot_id}
        raise ValueError(f"Device {device_name} not found in snapshot {snapshot_id}")

    def get_snapshot_topology(self, snapshot_id: str, **params) -> Dict[str, Any]:
        """Mock GET /api/snapshots/{snapshotId}/topology."""
        return {**MOCK_TOPOLOGY, "snapshotId": snapshot_id}

    def get_snapshot_metrics(self, snapshot_id: str) -> Dict[str, Any]:
        """Mock GET /api/snapshots/{snapshotId}/metrics."""
        return {**MOCK_METRICS, "snapshotId": snapshot_id}

    def get_snapshot_vulnerabilities(self, snapshot_id: str, **params) -> List[Dict[str, Any]]:
        """Mock GET /api/snapshots/{snapshotId}/vulnerabilities."""
        return MOCK_VULNERABILITIES


class MockNQEAPI:
    """Mock NQEAPI for testing."""

    def run_query(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mock POST /api/nqe."""
        query = data.get("query", "").lower()

        # Return different results based on query content
        if "ipaddresses" in query or "ip.address" in query or "interface.ipaddresses" in query:
            return MOCK_NQE_IP_QUERY_RESULT
        elif "vlans" in query or "vlan" in query:
            return MOCK_NQE_VLAN_QUERY_RESULT
        else:
            # Generic query result
            return {
                "status": "success",
                "data": [],
                "query": data.get("query"),
                "snapshotId": data.get("snapshotId", "$last"),
            }

    def get_queries(self) -> List[Dict[str, Any]]:
        """Mock GET /api/nqe/queries."""
        return [
            {
                "id": "query-1",
                "name": "Get All IP Addresses",
                "description": "Query to get all IP addresses in the network",
                "query": "foreach device in network.devices foreach interface in device.interfaces foreach ip in interface.ipAddresses select { device: device.name, interface: interface.name, address: ip.address }",
            },
            {
                "id": "query-2",
                "name": "Get All VLANs",
                "description": "Query to get all VLANs in the network",
                "query": "foreach vlan in network.vlans select { vid: vlan.id, name: vlan.name, description: vlan.description }",
            },
        ]

    def run_diff_query(self, before: str, after: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mock POST /api/nqe-diffs/{before}/{after}."""
        return {
            "status": "success",
            "beforeSnapshot": before,
            "afterSnapshot": after,
            "changes": [
                {"type": "added", "object": "device", "name": "new-device-01", "details": {"location": "datacenter-1"}},
                {"type": "removed", "object": "interface", "name": "Ethernet1/48", "device": "old-switch-01"},
            ],
        }


class MockForwardNetworksClient:
    """Mock ForwardNetworksClient for testing."""

    def __init__(self, base_url: str, username: str, password: str, verify_ssl: bool = True):
        """Initialize mock client."""
        self.base_url = base_url
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl

        # Initialize mock APIs
        self.networks = MockNetworkAPI()
        self.locations = MockLocationsAPI()
        self.devices = MockDevicesAPI()
        self.device_tags = MockDeviceTagsAPI()
        self.snapshots = MockSnapshotsAPI()
        self.collection = MockCollectionAPI()
        self.nqe = MockNQEAPI()

    def close(self):
        """Mock close method."""
        pass

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def create_mock_client(*args, **kwargs) -> MockForwardNetworksClient:
    """Create a mock Forward Networks client."""
    return MockForwardNetworksClient(*args, **kwargs)
