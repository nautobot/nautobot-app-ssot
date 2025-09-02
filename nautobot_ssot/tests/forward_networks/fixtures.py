"""Test fixtures for Forward Networks integration."""

# Mock Network Data
MOCK_NETWORKS = [
    {
        "id": "network-1",
        "name": "Production Network",
        "description": "Main production network",
        "status": "active",
        "created": "2024-01-01T00:00:00Z",
        "updated": "2024-01-15T12:00:00Z",
    },
    {
        "id": "network-2",
        "name": "Test Network",
        "description": "Testing environment network",
        "status": "active",
        "created": "2024-01-02T00:00:00Z",
        "updated": "2024-01-10T10:30:00Z",
    },
]

# Mock Location Data
MOCK_LOCATIONS = [
    {
        "id": "location-1",
        "name": "New York DC",
        "description": "Primary data center in New York",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "address": "123 Data Center Way, New York, NY 10001",
        "type": "datacenter",
    },
    {
        "id": "location-2",
        "name": "San Francisco Office",
        "description": "West coast office location",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "address": "456 Tech Street, San Francisco, CA 94105",
        "type": "office",
    },
]

# Mock Device Data
MOCK_DEVICES = [
    {
        "id": "device-1",
        "name": "ny-core-sw01",
        "hostname": "ny-core-sw01.example.com",
        "deviceType": "switch",
        "vendor": "Cisco",
        "model": "Nexus 9000",
        "serialNumber": "FCH12345678",
        "location": "location-1",
        "managementIp": "192.168.100.10",
        "platform": "nxos",
        "role": "core",
        "status": "active",
        "interfaces": [
            {
                "name": "Ethernet1/1",
                "description": "Link to ny-core-sw02",
                "type": "ethernet",
                "enabled": True,
                "mtu": 9000,
                "speed": 10000,
                "duplex": "full",
                "macAddress": "00:1A:2B:3C:4D:5E",
                "mode": "trunk",
                "vlan": None,
            },
            {
                "name": "Ethernet1/2",
                "description": "Link to ny-dist-sw01",
                "type": "ethernet",
                "enabled": True,
                "mtu": 1500,
                "speed": 1000,
                "duplex": "full",
                "macAddress": "00:1A:2B:3C:4D:5F",
                "mode": "access",
                "vlan": 100,
            },
        ],
    },
    {
        "id": "device-2",
        "name": "ny-fw01",
        "hostname": "ny-fw01.example.com",
        "deviceType": "firewall",
        "vendor": "Palo Alto",
        "model": "PA-3220",
        "serialNumber": "PA12345678",
        "location": "location-1",
        "managementIp": "192.168.100.20",
        "platform": "panos",
        "role": "firewall",
        "status": "active",
        "interfaces": [
            {
                "name": "ethernet1/1",
                "description": "Outside interface",
                "type": "ethernet",
                "enabled": True,
                "mtu": 1500,
                "speed": 1000,
                "duplex": "full",
                "macAddress": "00:1A:2B:3C:4D:60",
                "mode": "layer3",
                "vlan": None,
            },
            {
                "name": "ethernet1/2",
                "description": "Inside interface",
                "type": "ethernet",
                "enabled": True,
                "mtu": 1500,
                "speed": 1000,
                "duplex": "full",
                "macAddress": "00:1A:2B:3C:4D:61",
                "mode": "layer3",
                "vlan": None,
            },
        ],
    },
    {
        "id": "device-3",
        "name": "sf-access-sw01",
        "hostname": "sf-access-sw01.example.com",
        "deviceType": "switch",
        "vendor": "Arista",
        "model": "7050X-32",
        "serialNumber": "AR12345678",
        "location": "location-2",
        "managementIp": "192.168.200.10",
        "platform": "eos",
        "role": "access",
        "status": "active",
        "interfaces": [
            {
                "name": "Ethernet1",
                "description": "Uplink to distribution",
                "type": "ethernet",
                "enabled": True,
                "mtu": 1500,
                "speed": 10000,
                "duplex": "full",
                "macAddress": "00:1A:2B:3C:4D:70",
                "mode": "trunk",
                "vlan": None,
            }
        ],
    },
]

# Mock Snapshot Data
MOCK_SNAPSHOTS = [
    {
        "id": "snapshot-1",
        "networkId": "network-1",
        "name": "Daily Snapshot 2024-01-15",
        "created": "2024-01-15T02:00:00Z",
        "status": "processed",
        "isLatest": True,
    },
    {
        "id": "snapshot-2",
        "networkId": "network-1",
        "name": "Daily Snapshot 2024-01-14",
        "created": "2024-01-14T02:00:00Z",
        "status": "processed",
        "isLatest": False,
    },
]

# Mock NQE Query Results for IP Addresses
MOCK_NQE_IP_QUERY_RESULT = {
    "status": "success",
    "data": [
        {
            "device": "ny-core-sw01",
            "interface": "Vlan100",
            "address": "192.168.100.1/24",
            "prefix": "192.168.100.0/24",
            "version": 4,
        },
        {
            "device": "ny-core-sw01",
            "interface": "Loopback0",
            "address": "10.0.0.1/32",
            "prefix": "10.0.0.0/32",
            "version": 4,
        },
        {
            "device": "ny-fw01",
            "interface": "ethernet1/1",
            "address": "203.0.113.10/24",
            "prefix": "203.0.113.0/24",
            "version": 4,
        },
        {
            "device": "ny-fw01",
            "interface": "ethernet1/2",
            "address": "192.168.100.254/24",
            "prefix": "192.168.100.0/24",
            "version": 4,
        },
        {
            "device": "sf-access-sw01",
            "interface": "Vlan200",
            "address": "192.168.200.1/24",
            "prefix": "192.168.200.0/24",
            "version": 4,
        },
    ],
}

# Mock NQE Query Results for VLANs
MOCK_NQE_VLAN_QUERY_RESULT = {
    "status": "success",
    "data": [
        {"vid": 1, "name": "default", "description": "Default VLAN"},
        {"vid": 100, "name": "production", "description": "Production VLAN"},
        {"vid": 200, "name": "guest", "description": "Guest network VLAN"},
        {"vid": 300, "name": "management", "description": "Management VLAN"},
    ],
}

# Mock Device Tags
MOCK_DEVICE_TAGS = [
    {"name": "core", "description": "Core network devices", "color": "#ff0000"},
    {"name": "edge", "description": "Edge network devices", "color": "#00ff00"},
    {"name": "production", "description": "Production environment", "color": "#0000ff"},
]

# Mock Topology Data
MOCK_TOPOLOGY = {
    "nodes": [
        {"id": "ny-core-sw01", "name": "ny-core-sw01", "type": "switch", "location": "New York DC"},
        {"id": "ny-fw01", "name": "ny-fw01", "type": "firewall", "location": "New York DC"},
        {"id": "sf-access-sw01", "name": "sf-access-sw01", "type": "switch", "location": "San Francisco Office"},
    ],
    "links": [
        {
            "source": "ny-core-sw01",
            "target": "ny-fw01",
            "sourceInterface": "Ethernet1/10",
            "targetInterface": "ethernet1/2",
            "type": "ethernet",
        }
    ],
}

# Mock Metrics Data
MOCK_METRICS = {
    "deviceCount": 3,
    "interfaceCount": 15,
    "linkCount": 8,
    "vlanCount": 4,
    "prefixCount": 5,
    "lastCollectionTime": "2024-01-15T02:00:00Z",
    "collectionDuration": "00:15:30",
}

# Mock Vulnerability Data
MOCK_VULNERABILITIES = [
    {
        "id": "CVE-2023-1234",
        "severity": "high",
        "description": "Example vulnerability in network device firmware",
        "affectedDevices": ["ny-core-sw01"],
        "remediation": "Upgrade to firmware version 9.3.8",
        "published": "2023-12-01T00:00:00Z",
    },
    {
        "id": "CVE-2023-5678",
        "severity": "medium",
        "description": "Configuration vulnerability in firewall rules",
        "affectedDevices": ["ny-fw01"],
        "remediation": "Review and update firewall rule configuration",
        "published": "2023-11-15T00:00:00Z",
    },
]
