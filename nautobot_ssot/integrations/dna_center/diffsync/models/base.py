"""DiffSyncModel subclasses for Nautobot-to-DNA Center data sync."""

from typing import List, Optional
from uuid import UUID

from diffsync import DiffSyncModel


class Area(DiffSyncModel):
    """DiffSync model for DNA Center areas."""

    _modelname = "area"
    _identifiers = ("name", "parent", "parent_of_parent")
    _attributes = ("metadata",)
    _children = {}

    name: str
    parent: Optional[str] = None
    parent_of_parent: Optional[str] = None
    metadata: Optional[bool] = True

    uuid: Optional[UUID] = None


class Building(DiffSyncModel):
    """DiffSync model for DNA Center buildings."""

    _modelname = "building"
    _identifiers = ("name", "area")
    _attributes = ("address", "area_parent", "latitude", "longitude", "tenant", "metadata")
    _children = {"floor": "floors"}

    name: str
    address: Optional[str] = None
    area: Optional[str] = None
    area_parent: Optional[str] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    tenant: Optional[str] = None
    floors: Optional[List["Floor"]] = []
    metadata: Optional[bool] = True

    uuid: Optional[UUID] = None


class Floor(DiffSyncModel):
    """DiffSync model for DNA Center floors."""

    _modelname = "floor"
    _identifiers = ("name", "building", "area")
    _attributes = ("tenant", "metadata")
    _children = {}

    name: str
    building: str
    area: str
    tenant: Optional[str] = None
    metadata: Optional[bool] = True

    uuid: Optional[UUID] = None


class Device(DiffSyncModel):
    """DiffSync model for DNA Center devices."""

    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "area",
        "site",
        "serial",
        "status",
        "role",
        "vendor",
        "model",
        "floor",
        "version",
        "platform",
        "tenant",
        "controller_group",
        "metadata",
    )
    _children = {"port": "ports"}

    name: Optional[str] = None
    status: Optional[str] = None
    role: Optional[str] = None
    vendor: str
    model: str
    area: str
    site: str
    floor: Optional[str] = None
    serial: str = ""
    version: Optional[str] = None
    platform: str
    tenant: Optional[str] = None
    controller_group: str
    ports: Optional[List["Port"]] = []
    metadata: Optional[bool] = True

    uuid: Optional[UUID] = None


class Port(DiffSyncModel):
    """DiffSync model for DNA Center interfaces."""

    _modelname = "port"
    _identifiers = ("name", "device")
    _attributes = ("description", "mac_addr", "port_type", "port_mode", "mtu", "status", "enabled", "metadata")
    _children = {}

    name: str
    device: str
    description: Optional[str] = None
    port_type: str
    port_mode: str
    mac_addr: Optional[str] = None
    mtu: int
    status: str
    enabled: bool
    metadata: Optional[bool] = True

    uuid: Optional[UUID] = None


class Prefix(DiffSyncModel):
    """DiffSync Model for DNA Center prefixes."""

    _modelname = "prefix"
    _identifiers = ("prefix", "namespace")
    _attributes = ("tenant", "metadata")
    _children = {}

    prefix: str
    namespace: str
    tenant: Optional[str] = None
    metadata: Optional[bool] = True

    uuid: Optional[UUID] = None


class IPAddress(DiffSyncModel):
    """DiffSync model for DNA Center IP addresses."""

    _modelname = "ipaddress"
    _identifiers = ("host", "namespace")
    _attributes = ("mask_length", "tenant", "metadata")
    _children = {}

    host: str
    mask_length: int
    namespace: str
    tenant: Optional[str] = None
    metadata: Optional[bool] = True

    uuid: Optional[UUID] = None


class IPAddressOnInterface(DiffSyncModel):
    """DiffSync model for DNA Center tracking IPAddress on particular Device interfaces."""

    _modelname = "ip_on_intf"
    _identifiers = ("host", "device", "port")
    _attributes = ("primary",)
    _children = {}

    host: str
    device: str
    port: str
    primary: bool

    uuid: Optional[UUID] = None


Area.model_rebuild()
Building.model_rebuild()
Device.model_rebuild()
