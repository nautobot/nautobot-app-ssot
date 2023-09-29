"""Base DCIM subclasses DiffSyncModel for nautobot_ssot_device42 data sync."""

from typing import List, Optional
from uuid import UUID

from diffsync import DiffSyncModel


class Building(DiffSyncModel):
    """Base Building model."""

    _modelname = "building"
    _identifiers = ("name",)
    _attributes = ("address", "latitude", "longitude", "contact_name", "contact_phone", "tags", "custom_fields")
    _children = {"room": "rooms"}
    name: str
    address: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    contact_name: Optional[str]
    contact_phone: Optional[str]
    rooms: List["Room"] = list()
    tags: Optional[List[str]]
    custom_fields: Optional[dict]
    uuid: Optional[UUID]


class Room(DiffSyncModel):
    """Base Room model."""

    _modelname = "room"
    _identifiers = ("name", "building")
    _attributes = ("notes", "custom_fields")
    _children = {"rack": "racks"}
    name: str
    building: str
    notes: Optional[str]
    racks: List["Rack"] = list()
    custom_fields: Optional[dict]
    uuid: Optional[UUID]


class Rack(DiffSyncModel):
    """Base Rack model."""

    _modelname = "rack"
    _identifiers = ("name", "building", "room")
    _attributes = ("height", "numbering_start_from_bottom", "tags", "custom_fields")
    _children = {}
    name: str
    building: str
    room: str
    height: int
    numbering_start_from_bottom: str
    tags: Optional[List[str]]
    custom_fields: Optional[dict]
    uuid: Optional[UUID]


class Vendor(DiffSyncModel):
    """Base Vendor model."""

    _modelname = "vendor"
    _identifiers = ("name",)
    _attributes = ("custom_fields",)
    _children = {}
    name: str
    custom_fields: Optional[dict]
    uuid: Optional[UUID]


class Hardware(DiffSyncModel):
    """Base Hardware model."""

    _modelname = "hardware"
    _identifiers = ("name",)
    _attributes = ("manufacturer", "size", "depth", "part_number", "custom_fields")
    _children = {}
    name: str
    manufacturer: str
    size: float
    depth: Optional[str]
    part_number: Optional[str]
    custom_fields: Optional[dict]
    uuid: Optional[UUID]


class Cluster(DiffSyncModel):
    """Base Cluster model."""

    _modelname = "cluster"
    _identifiers = ("name",)
    _attributes = ("tags", "custom_fields")
    _children = {}
    name: str
    members: Optional[List[str]]
    tags: Optional[List[str]]
    custom_fields: Optional[dict]
    uuid: Optional[UUID]


class Device(DiffSyncModel):
    """Device42 Device model."""

    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "building",
        "room",
        "rack",
        "rack_position",
        "rack_orientation",
        "hardware",
        "os",
        "os_version",
        "in_service",
        "serial_no",
        "tags",
        "cluster_host",
        "master_device",
        "custom_fields",
        "vc_position",
    )
    _children = {"port": "interfaces"}
    name: str
    building: str
    room: Optional[str]
    rack: Optional[str]
    rack_position: Optional[float]
    rack_orientation: Optional[str]
    hardware: str
    os: Optional[str]
    os_version: Optional[str]
    in_service: Optional[bool]
    interfaces: Optional[List["Port"]] = []
    serial_no: Optional[str]
    tags: Optional[List[str]]
    cluster_host: Optional[str]
    master_device: bool
    vc_position: Optional[int]
    custom_fields: Optional[dict]
    uuid: Optional[UUID]


class Port(DiffSyncModel):
    """Base Port model."""

    _modelname = "port"
    _identifiers = ("device", "name")
    _attributes = (
        "enabled",
        "mtu",
        "description",
        "mac_addr",
        "type",
        "mode",
        "status",
        "tags",
        "vlans",
        "custom_fields",
    )
    _children = {}
    name: str
    device: str
    enabled: Optional[bool]
    mtu: Optional[int]
    description: Optional[str]
    mac_addr: Optional[str]
    type: str
    tags: Optional[List[str]]
    mode: str
    status: str
    vlans: Optional[List[int]] = []
    custom_fields: Optional[dict]
    uuid: Optional[UUID]


class Connection(DiffSyncModel):
    """Base Connection model."""

    _modelname = "conn"
    _identifiers = ("src_device", "src_port", "src_port_mac", "dst_device", "dst_port", "dst_port_mac")
    _attributes = ("src_type", "dst_type")
    _children = {}

    src_device: str
    src_port: str
    src_type: str
    src_port_mac: Optional[str]
    dst_device: str
    dst_port: str
    dst_type: str
    dst_port_mac: Optional[str]
    tags: Optional[List[str]]
    uuid: Optional[UUID]


Building.update_forward_refs()
Room.update_forward_refs()
Device.update_forward_refs()
