"""DiffSyncModel subclasses for Nautobot-to-LibreNMS data sync."""

from typing import List, Optional
from uuid import UUID

from diffsync import DiffSyncModel


class Location(DiffSyncModel):
    """DiffSync Model for LibreNMS Location."""

    _modelname = "location"
    _identifiers = ("name",)
    _attributes = (
        "status",
        "location_type",
        "tenant",
        "parent",
        "latitude",
        "longitude",
        "system_of_record",
    )
    _children = {}

    name: str
    status: str
    location_type: str
    tenant: Optional[str] = None
    parent: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    system_of_record: str

    uuid: Optional[UUID] = None


class Device(DiffSyncModel):
    """DiffSync Model for LibreNMS Device."""

    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "device_id",
        "location",
        "tenant",
        "status",
        "device_type",
        "role",
        "manufacturer",
        "platform",
        "os_version",
        "serial_no",
        "tags",
        "system_of_record",
    )
    _children = {"port": "interfaces"}

    name: str
    device_id: Optional[int] = None
    location: str
    tenant: Optional[str] = None
    status: str
    device_type: str
    ip_address: Optional[str] = None
    role: Optional[str] = None
    manufacturer: str
    platform: Optional[str] = None
    os_version: Optional[str] = None
    interfaces: Optional[List["Port"]] = []
    serial_no: Optional[str] = None
    tags: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


class Port(DiffSyncModel):
    """DiffSync Model for LibreNMS Port."""

    _modelname = "port"
    _identifiers = ("device", "name")
    _attributes = (
        "status",
        "mtu",
        "description",
        "mac_addr",
        "interface_type",
        "tags",
        "mode",
        "vlans",
        "system_of_record",
    )
    _children = {}

    name: str
    device: str
    status: Optional[bool] = False
    mtu: Optional[int] = None
    description: Optional[str] = None
    mac_addr: Optional[str] = None
    interface_type: Optional[str] = None
    tags: Optional[List[str]] = None
    mode: Optional[str] = None
    vlans: Optional[List[int]] = []
    system_of_record: str

    uuid: Optional[UUID] = None


class Prefix(DiffSyncModel):
    """DiffSync model for LibreNMS Prefix."""

    _modelname = "prefix"
    _identifiers = (
        "network",
        "tenant",
        "mask_bits",
        "vrf",
    )
    _attributes = ("description", "tags", "system_of_record")
    _children = {}
    network: str
    tenant: Optional[str] = None
    mask_bits: int
    description: Optional[str] = None
    vrf: Optional[str] = None
    tags: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


class IPAddress(DiffSyncModel):
    """DiffSync Model for LibreNMS IPAddress."""

    _modelname = "ip_address"
    _identifiers = ("address", "subnet")
    _attributes = (
        "namespace",
        "available",
        "tenant",
        "label",
        "device",
        "interface",
        "primary",
        "tags",
        "system_of_record",
    )
    _children = {}

    address: str
    subnet: str
    namespace: str
    available: bool
    tenant: Optional[str] = None
    label: Optional[str] = None
    device: Optional[str] = None
    interface: Optional[str] = None
    primary: Optional[bool] = None
    tags: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


class Connection(DiffSyncModel):
    """DiffSync Model for LibreNMS Connection."""

    _modelname = "conn"
    _identifiers = (
        "src_device",
        "src_port",
        "src_port_mac",
        "dst_device",
        "dst_port",
        "dst_port_mac",
    )
    _attributes = ("src_type", "dst_type", "system_of_record")
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
    system_of_record: str

    uuid: Optional[UUID] = None


class SSoTJob(DiffSyncModel):
    """DiffSync model for LibreNMS SSoTJobs."""

    _modelname = "ssot-job"
    _identifiers = (
        "name",
        "schedule",
    )
    _attributes = ()
    _children = {}

    name: str
    schedule: str

    uuid: Optional[UUID] = None


Device.model_rebuild()
