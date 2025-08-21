# pylint: disable=duplicate-code
"""DiffSyncModel subclasses for Nautobot-to-Citrix ADM data sync."""

from typing import List, Optional
from uuid import UUID

from diffsync import DiffSyncModel
from diffsync.enum import DiffSyncModelFlags


class Datacenter(DiffSyncModel):
    """Diffsync model for Citrix ADM datacenters."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _modelname = "datacenter"
    _identifiers = (
        "name",
        "region",
    )
    _attributes = ("latitude", "longitude")

    name: str
    region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    uuid: Optional[UUID] = None


class OSVersion(DiffSyncModel):
    """DiffSync model for Citrix ADM device OS versions."""

    _modelname = "osversion"
    _identifiers = ("version",)
    _attributes = ()

    version: str

    uuid: Optional[UUID] = None


class Device(DiffSyncModel):
    """DiffSync model for Citrix ADM devices."""

    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "model",
        "role",
        "serial",
        "site",
        "status",
        "tenant",
        "version",
        "hanode",
    )
    _children = {"port": "ports"}

    name: str
    model: Optional[str] = None
    role: str
    serial: Optional[str] = None
    site: Optional[str] = None
    status: Optional[str] = None
    tenant: Optional[str] = None
    version: Optional[str] = None
    ports: Optional[List["Port"]] = []
    hanode: Optional[str] = None

    uuid: Optional[UUID] = None


class Port(DiffSyncModel):
    """DiffSync model for Citrix ADM device interfaces."""

    _modelname = "port"
    _identifiers = ("name", "device")
    _attributes = ("status", "description")
    _children = {}

    name: str
    device: str
    status: str
    description: Optional[str] = None

    uuid: Optional[UUID] = None


class Subnet(DiffSyncModel):
    """DiffSync model for Citrix ADM management prefixes."""

    _modelname = "prefix"
    _identifiers = ("prefix", "namespace")
    _attributes = ("tenant",)
    _children = {}

    prefix: str
    namespace: str
    tenant: Optional[str] = None

    uuid: Optional[UUID] = None


class Address(DiffSyncModel):
    """DiffSync model for Citrix ADM IP Addresses."""

    _modelname = "address"
    _identifiers = ("host_address", "tenant")
    _attributes = ("mask_length", "prefix", "tags")
    _children = {}

    host_address: str
    mask_length: int
    prefix: str
    tenant: Optional[str] = None
    tags: Optional[list] = None

    uuid: Optional[UUID] = None


class IPAddressOnInterface(DiffSyncModel):
    """DiffSync model for Citrix ADM tracking IPAddress on particular Device interfaces."""

    _modelname = "ip_on_intf"
    _identifiers = ("host_address", "device", "port")
    _attributes = ("primary",)
    _children = {}

    host_address: str
    device: str
    port: str
    primary: bool

    uuid: Optional[UUID] = None
