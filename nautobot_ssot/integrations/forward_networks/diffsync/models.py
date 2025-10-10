"""DiffSync models for Forward Networks integration."""

from typing import List, Optional
from uuid import UUID

from diffsync import DiffSyncModel


class Network(DiffSyncModel):
    """Forward Networks Network model."""

    _modelname = "network"
    _identifiers = ("name",)
    _attributes = ("network_id", "description", "status", "tags", "custom_fields")
    _children = {"device": "devices", "location": "locations"}

    name: str
    network_id: str
    description: Optional[str] = None
    status: Optional[str] = "Active"
    devices: List["Device"] = []
    locations: List["Location"] = []
    tags: Optional[List[str]] = None
    custom_fields: Optional[dict] = None
    uuid: Optional[UUID] = None


class Location(DiffSyncModel):
    """Forward Networks Location model."""

    _modelname = "location"
    _identifiers = ("name", "network")
    _attributes = ("location_id", "description", "location_type", "latitude", "longitude", "tags", "custom_fields")
    _children = {"device": "devices"}

    name: str
    network: str
    location_id: str
    description: Optional[str] = None
    location_type: str = "Site"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    devices: List["Device"] = []
    tags: Optional[List[str]] = None
    custom_fields: Optional[dict] = None
    uuid: Optional[UUID] = None


class Device(DiffSyncModel):
    """Forward Networks Device model."""

    _modelname = "device"
    _identifiers = ("name", "network")
    _attributes = (
        "device_id",
        "device_type",
        "manufacturer",
        "model",
        "serial_number",
        "location",
        "primary_ip",
        "platform",
        "status",
        "role",
        "tags",
        "custom_fields",
    )
    _children = {"interface": "interfaces", "ip_address": "ip_addresses"}

    name: str
    network: str
    device_id: str
    device_type: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    location: Optional[str] = None
    primary_ip: Optional[str] = None
    platform: Optional[str] = None
    status: str = "Active"
    role: Optional[str] = None
    interfaces: List["Interface"] = []
    ip_addresses: List["IPAddress"] = []
    tags: Optional[List[str]] = None
    custom_fields: Optional[dict] = None
    uuid: Optional[UUID] = None


class Interface(DiffSyncModel):
    """Forward Networks Interface model."""

    _modelname = "interface"
    _identifiers = ("name", "device", "network")
    _attributes = (
        "description",
        "interface_type",
        "enabled",
        "mtu",
        "speed",
        "duplex",
        "mac_address",
        "mode",
        "vlan",
        "status",
        "tags",
        "custom_fields",
    )
    _children = {"ip_address": "ip_addresses"}

    name: str
    device: str
    network: str
    description: Optional[str] = None
    interface_type: str = "other"
    enabled: bool = True
    mtu: Optional[int] = None
    speed: Optional[int] = None
    duplex: Optional[str] = None
    mac_address: Optional[str] = None
    mode: Optional[str] = None
    vlan: Optional[str] = None
    status: str = "Active"
    ip_addresses: List["IPAddress"] = []
    tags: Optional[List[str]] = None
    custom_fields: Optional[dict] = None
    uuid: Optional[UUID] = None


class IPAddress(DiffSyncModel):
    """Forward Networks IP Address model."""

    _modelname = "ip_address"
    _identifiers = ("address", "network")
    _attributes = (
        "ip_version",
        "description",
        "status",
        "role",
        "device",
        "interface",
        "prefix",
        "tags",
        "custom_fields",
    )
    _children = {}

    address: str
    network: str
    ip_version: int = 4
    description: Optional[str] = None
    status: str = "Active"
    role: Optional[str] = None
    device: Optional[str] = None
    interface: Optional[str] = None
    prefix: Optional[str] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[dict] = None
    uuid: Optional[UUID] = None


class Prefix(DiffSyncModel):
    """Forward Networks Prefix model."""

    _modelname = "prefix"
    _identifiers = ("prefix", "network")
    _attributes = (
        "description",
        "prefix_type",
        "status",
        "role",
        "location",
        "vlan",
        "tags",
        "custom_fields",
    )
    _children = {"ip_address": "ip_addresses"}

    prefix: str
    network: str
    description: Optional[str] = None
    prefix_type: str = "network"
    status: str = "Active"
    role: Optional[str] = None
    location: Optional[str] = None
    vlan: Optional[str] = None
    ip_addresses: List["IPAddress"] = []
    tags: Optional[List[str]] = None
    custom_fields: Optional[dict] = None
    uuid: Optional[UUID] = None


class VLAN(DiffSyncModel):
    """Forward Networks VLAN model."""

    _modelname = "vlan"
    _identifiers = ("vid", "network")
    _attributes = (
        "name",
        "description",
        "status",
        "role",
        "location",
        "tags",
        "custom_fields",
    )
    _children = {}

    vid: int
    network: str
    name: Optional[str] = None
    description: Optional[str] = None
    status: str = "Active"
    role: Optional[str] = None
    location: Optional[str] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[dict] = None
    uuid: Optional[UUID] = None


# Update forward references for circular dependencies
Network.update_forward_refs()
Location.update_forward_refs()
Device.update_forward_refs()
Interface.update_forward_refs()
IPAddress.update_forward_refs()
Prefix.update_forward_refs()
VLAN.update_forward_refs()
