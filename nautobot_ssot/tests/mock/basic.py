data = {
    "vlan": {
        "ams01__101": {
            "site": "ams01",
            "vid": 101,
            "name": "VL101",
            "status": "active",
        },
        "ams01__102": {
            "site": "ams01",
            "vid": 102,
            "name": "VL102",
            "status": "active",
        },
        "ams01__103": {
            "site": "ams01",
            "vid": 103,
            "name": "VL103",
            "status": "active",
        },
    },
    "interface": {
        "ams01-edge-01__vlan101": {
            "device": "ams01-edge-01",
            "name": "vlan101",
            "description": "",
            "type": "10gbase-t",
            "mode": "access",
        },
        "ams01-edge-01__Ethernet1/1": {
            "device": "ams01-edge-01",
            "name": "Ethernet1/1",
            "description": "",
            "type": "10gbase-t",
            "mode": "access",
        },
        "ams01-edge-01__Ethernet2/1": {
            "device": "ams01-edge-01",
            "name": "Ethernet2/1",
            "description": "",
            "type": "10gbase-t",
            "mode": "access",
        },
        "ams01-edge-01__PortChannel1": {
            "device": "ams01-edge-01",
            "name": "PortChannel1",
            "description": "",
            "type": "10gbase-t",
            "mode": "access",
        },
        "ams01-edge-01__Ethernet3/1": {
            "device": "ams01-edge-01",
            "name": "Ethernet3/1",
            "description": "",
            "type": "10gbase-t",
            "mode": "access",
        },
        "ams01-edge-01__Ethernet4/1": {
            "device": "ams01-edge-01",
            "name": "Ethernet4/1",
            "description": "",
            "type": "10gbase-t",
            "mode": "access",
            "tagged_vlans": ["ams01__102", "ams01__103"],
            "untagged_vlan": "ams01__101",
        },
        "ams01-edge-01__Loopback0": {
            "device": "ams01-edge-01",
            "name": "Loopback0",
            "description": "",
            "type": "10gbase-t",
            "mode": "access",
        },
        "ams01-edge-02__vlan102": {
            "device": "ams01-edge-02",
            "name": "vlan102",
            "description": "",
            "type": "10gbase-t",
            "mode": "access",
        },
        "ams01-edge-02__Ethernet1/1": {
            "device": "ams01-edge-02",
            "name": "Ethernet1/1",
            "description": "",
            "type": "10gbase-t",
            "mode": "access",
        },
        "ams01-edge-02__Ethernet2/1": {
            "device": "ams01-edge-02",
            "name": "Ethernet2/1",
            "description": "",
            "type": "10gbase-t",
            "mode": "access",
        },
        "ams01-edge-02__Loopback0": {
            "device": "ams01-edge-02",
            "name": "Loopback0",
            "description": "",
            "type": "10gbase-t",
            "mode": "access",
        },
        "ams01-edge-03__vlan103": {
            "device": "ams01-edge-03",
            "name": "vlan103",
            "description": "",
            "type": "10gbase-t",
            "mode": "access",
        },
        "ams01-edge-03__Ethernet1/1": {
            "device": "ams01-edge-03",
            "name": "Ethernet1/1",
            "description": "",
            "type": "10gbase-t",
            "mode": "access",
        },
        "ams01-edge-03__Ethernet2/1": {
            "device": "ams01-edge-03",
            "name": "Ethernet2/1",
            "description": "",
            "type": "10gbase-t",
            "mode": "access",
        },
        "ams01-edge-03__Loopback0": {
            "device": "ams01-edge-03",
            "name": "Loopback0",
            "description": "",
            "type": "10gbase-t",
            "mode": "access",
        },
    },
    "site": {
        "ams01": {
            "slug": "ams01",
            "name": "ams01",
            "devices": ["ams01-edge-01", "ams01-edge-02", "ams01-edge-03"],
            "vlans": ["ams01__101", "ams01__102", "ams01__103"],
        }
    },
    "device": {
        "ams01-edge-01": {
            "name": "ams01-edge-01",
            "site": "ams01",
            "interfaces": [
                "ams01-edge-01__vlan101",
                "ams01-edge-01__Ethernet1/1",
                "ams01-edge-01__Ethernet2/1",
                "ams01-edge-01__Ethernet3/1",
                "ams01-edge-01__Ethernet4/1",
                "ams01-edge-01__PortChannel1",
                "ams01-edge-01__Loopback0",
            ],
        },
        "ams01-edge-02": {
            "name": "ams01-edge-02",
            "site": "ams01",
            "interfaces": [
                "ams01-edge-02__vlan102",
                "ams01-edge-02__Ethernet1/1",
                "ams01-edge-02__Ethernet2/1",
                "ams01-edge-02__Loopback0",
            ],
        },
        "ams01-edge-03": {
            "name": "ams01-edge-03",
            "site": "ams01",
            "interfaces": [
                "ams01-edge-03__vlan103",
                "ams01-edge-03__Ethernet1/1",
                "ams01-edge-03__Ethernet2/1",
                "ams01-edge-03__Loopback0",
            ],
        },
    },
    "status": {
        "planned": {
            "slug": "planned",
            "name": "Planned",
        },
        "provisioning": {
            "slug": "provisioning",
            "name": "Provisioning",
        },
        "active": {
            "slug": "active",
            "name": "Active",
        },
        "offline": {
            "slug": "offline",
            "name": "Offline",
        },
        "deprovisioning": {
            "slug": "deprovisioning",
            "name": "Deprovisioning",
        },
        "decommissioned": {
            "slug": "decommissioned",
            "name": "Decommissioned",
        },
        "connected": {
            "slug": "connected",
            "name": "Connected",
        },
        "decommissioning": {
            "slug": "decommissioning",
            "name": "Decommissioning",
        },
        "staged": {
            "slug": "staged",
            "name": "Staged",
        },
        "failed": {
            "slug": "failed",
            "name": "Failed",
        },
        "inventory": {
            "slug": "inventory",
            "name": "Inventory",
        },
        "maintenance": {
            "slug": "maintenance",
            "name": "Maintenance",
        },
        "staging": {
            "slug": "staging",
            "name": "Staging",
        },
        "retired": {
            "slug": "retired",
            "name": "Retired",
        },
        "reserved": {
            "slug": "reserved",
            "name": "Reserved",
        },
        "available": {
            "slug": "available",
            "name": "Available",
        },
        "deprecated": {
            "slug": "deprecated",
            "name": "Deprecated",
        },
        "dhcp": {
            "slug": "dhcp",
            "name": "DHCP",
        },
        "slaac": {
            "slug": "slaac",
            "name": "SLAAC",
        },
        "container": {
            "slug": "container",
            "name": "Container",
        },
    },
}
