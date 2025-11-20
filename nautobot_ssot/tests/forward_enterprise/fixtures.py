"""Test fixtures for Forward Enterprise integration."""

from unittest.mock import MagicMock


class DummyJob:
    """Mock job for testing."""

    def __init__(self):
        self.logger = MagicMock()
        self.credentials = MagicMock()
        self.credentials.extra_config = {}
        # Set up proper mock values for the API URL and token
        self.credentials.remote_url = "https://test.example.com/"
        self.credentials.verify_ssl = True

        # Mock the secrets group
        mock_secrets_group = MagicMock()
        mock_secrets_group.get_secret_value.return_value = "test_token"
        self.credentials.secrets_group = mock_secrets_group


# Mock NQE Device Query Result (based on your actual Forward Enterprise queries)
MOCK_NQE_DEVICE_QUERY_RESULT = {
    "snapshotId": "393879",
    "items": [
        {
            "location": "compute-pod300",
            "manufacturer": "ARISTA",
            "device_type": "vEOS",
            "role": "ROUTER",
            "name": "sjc-dc12-acc305",
            "serial": [""],
            "status": "active",
            "tags": [],
        },
        {
            "location": "compute-pod000",
            "manufacturer": "ARISTA",
            "device_type": "vEOS",
            "role": "ROUTER",
            "name": "sjc-dc12-acc012",
            "serial": [""],
            "status": "active",
            "tags": [],
        },
        {
            "location": "compute-pod200",
            "manufacturer": "ARISTA",
            "device_type": "vEOS",
            "role": "ROUTER",
            "name": "sjc-dc12-acc207",
            "serial": [""],
            "status": "active",
            "tags": [],
        },
        {
            "location": "atl-dc",
            "manufacturer": "F5",
            "device_type": "BIG-IP Virtual Edition",
            "role": "LOAD_BALANCER",
            "name": "atl-app-lb01",
            "serial": ["00000000-0000-0000-000000000000"],
            "status": "active",
            "tags": [],
        },
    ],
}

# Mock NQE Interface Query Result
MOCK_NQE_INTERFACE_QUERY_RESULT = {
    "snapshotId": "393879",
    "items": [
        {
            "device": "sjc-dc12-acc305",
            "location": "Compute-Pod300",
            "name": "et1",
            "enabled": "1",
            "mtu": 1500,
            "mac_address": "00:07:00:CC:A5:53",
            "speed": "SPEED_UNKNOWN",
            "duplex": "full",
        },
        {
            "device": "sjc-dc12-acc305",
            "location": "Compute-Pod300",
            "name": "ma1",
            "enabled": "1",
            "mtu": 1500,
            "mac_address": "00:07:00:00:00:17",
            "speed": "SPEED_1GB",
            "duplex": "full",
        },
        {
            "device": "sjc-dc12-acc012",
            "location": "Compute-Pod000",
            "name": "et1",
            "enabled": "1",
            "mtu": 1500,
            "mac_address": "00:20:00:9C:DA:72",
            "speed": "SPEED_UNKNOWN",
            "duplex": "full",
        },
        {
            "device": "sjc-dc12-acc012",
            "location": "Compute-Pod000",
            "name": "et2",
            "enabled": "1",
            "mtu": 1500,
            "mac_address": "00:20:00:9C:DA:72",
            "speed": "SPEED_UNKNOWN",
            "duplex": "full",
        },
    ],
}

# Mock NQE IPAM Query Result
MOCK_NQE_IPAM_QUERY_RESULT = {
    "snapshotId": "393879",
    "items": [
        {
            "location": "Compute-Pod300",
            "device": "sjc-dc12-acc305",
            "interface": "et1",
            "vrf": "default",
            "ip": "10.100.0.134",
            "prefixLength": 31,
        },
        {
            "location": "Compute-Pod300",
            "device": "sjc-dc12-acc305",
            "interface": "lo0",
            "vrf": "default",
            "ip": "10.117.255.65",
            "prefixLength": 32,
        },
        {
            "location": "Compute-Pod300",
            "device": "sjc-dc12-acc305",
            "interface": "ma1",
            "vrf": "management",
            "ip": "10.117.38.51",
            "prefixLength": 24,
        },
        {
            "location": "Compute-Pod000",
            "device": "sjc-dc12-acc012",
            "interface": "et1",
            "vrf": "default",
            "ip": "10.100.0.76",
            "prefixLength": 31,
        },
        {
            "location": "Compute-Pod000",
            "device": "sjc-dc12-acc012",
            "interface": "lo0",
            "vrf": "default",
            "ip": "10.117.255.12",
            "prefixLength": 32,
        },
        {
            "location": "Compute-Pod000",
            "device": "sjc-dc12-acc012",
            "interface": "ma1",
            "vrf": "management",
            "ip": "10.117.38.22",
            "prefixLength": 24,
        },
        {
            "location": "Compute-Pod200",
            "device": "sjc-dc12-acc207",
            "interface": "et1",
            "vrf": "default",
            "ip": "10.100.0.174",
            "prefixLength": 31,
        },
        {
            "location": "Compute-Pod200",
            "device": "sjc-dc12-acc207",
            "interface": "lo0",
            "vrf": "default",
            "ip": "10.117.255.47",
            "prefixLength": 32,
        },
    ],
}

# Query mappings for mocking NQE API calls
NQE_QUERY_MAPPINGS = {
    "device_query": MOCK_NQE_DEVICE_QUERY_RESULT,
    "interface_query": MOCK_NQE_INTERFACE_QUERY_RESULT,
    "ipam_query": MOCK_NQE_IPAM_QUERY_RESULT,
}
