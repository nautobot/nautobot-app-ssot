"""Base DCIM subclasses DiffSyncModel for nautobot_ssot_device42 data sync."""

from typing import List, Optional
from uuid import UUID

from diffsync import DiffSyncModel


class Building(DiffSyncModel):
    """Base Building model."""

    _modelname = "building"
    _identifiers = ("name", "location_type")
    _attributes = ("address", "latitude", "longitude", "contact_name", "contact_phone", "tags", "custom_fields")
    _children = {"room": "rooms"}
    name: str
    location_type: str
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    rooms: List["Room"] = []
    tags: Optional[List[str]] = None
    custom_fields: Optional[dict] = None
    uuid: Optional[UUID] = None


class Room(DiffSyncModel):
    """Base Room model."""

    _modelname = "room"
    _identifiers = ("name", "building", "building_loctype")
    _attributes = ("notes", "custom_fields")
    _children = {"rack": "racks"}
    name: str
    building: str
    building_loctype: str
    notes: Optional[str] = None
    racks: List["Rack"] = []
    custom_fields: Optional[dict] = None
    uuid: Optional[UUID] = None


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
    tags: Optional[List[str]] = None
    custom_fields: Optional[dict] = None
    uuid: Optional[UUID] = None


class Vendor(DiffSyncModel):
    """Base Vendor model."""

    _modelname = "vendor"
    _identifiers = ("name",)
    _attributes = ("custom_fields",)
    _children = {}
    name: str
    custom_fields: Optional[dict] = None
    uuid: Optional[UUID] = None


class Hardware(DiffSyncModel):
    """Base Hardware model."""

    _modelname = "hardware"
    _identifiers = ("name",)
    _attributes = ("manufacturer", "size", "depth", "part_number", "custom_fields")
    _children = {}
    name: str
    manufacturer: str
    size: float
    depth: Optional[str] = None
    part_number: Optional[str] = None
    custom_fields: Optional[dict] = None
    uuid: Optional[UUID] = None


class Cluster(DiffSyncModel):
    """Base Cluster model."""

    _modelname = "cluster"
    _identifiers = ("name",)
    _attributes = ("tags", "custom_fields")
    _children = {}
    name: str
    members: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[dict] = None
    uuid: Optional[UUID] = None


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
    room: Optional[str] = None
    rack: Optional[str] = None
    rack_position: Optional[float] = None
    rack_orientation: Optional[str] = None
    hardware: str
    os: Optional[str]
    os_version: Optional[str] = None
    in_service: Optional[bool] = None
    interfaces: Optional[List["Port"]] = []
    serial_no: Optional[str] = None
    tags: Optional[List[str]] = None
    cluster_host: Optional[str] = None
    master_device: bool
    vc_position: Optional[int] = None
    custom_fields: Optional[dict] = None
    uuid: Optional[UUID] = None


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
    enabled: Optional[bool] = None
    mtu: Optional[int] = None
    description: Optional[str] = None
    mac_addr: Optional[str] = None
    type: str
    tags: Optional[List[str]] = None
    mode: str
    status: str
    vlans: Optional[List[int]] = []
    custom_fields: Optional[dict] = None
    uuid: Optional[UUID] = None


class Connection(DiffSyncModel):
    """Base Connection model."""

    _modelname = "conn"
    _identifiers = ("src_device", "src_port", "src_port_mac", "dst_device", "dst_port", "dst_port_mac")
    _attributes = ("src_type", "dst_type")
    _children = {}

    src_device: str
    src_port: str
    src_type: str
    src_port_mac: Optional[str] = None
    dst_device: str
    dst_port: str
    dst_type: str
    dst_port_mac: Optional[str] = None
    tags: Optional[List[str]] = None
    uuid: Optional[UUID] = None


Building.model_rebuild()
Room.model_rebuild()
Device.model_rebuild()
