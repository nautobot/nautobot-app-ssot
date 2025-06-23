"""DiffSyncModel subclasses for Nautobot-to-Meraki data sync."""

from typing import List, Optional
from uuid import UUID

from diffsync import DiffSyncModel
from diffsync.enum import DiffSyncModelFlags


class Network(DiffSyncModel):
    """DiffSync model for Meraki networks."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _modelname = "network"
    _identifiers = (
        "name",
        "parent",
    )
    _attributes = ("timezone", "notes", "tags", "tenant")
    _children = {}

    name: str
    parent: Optional[str] = None
    timezone: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    tenant: Optional[str] = None

    uuid: Optional[UUID] = None


class Hardware(DiffSyncModel):
    """DiffSync model for Meraki models."""

    _modelname = "hardware"
    _identifiers = ("model",)
    _attributes = ()
    _children = {}

    model: str

    uuid: Optional[UUID] = None


class OSVersion(DiffSyncModel):
    """DiffSync model for Meraki device software versions."""

    _modelname = "osversion"
    _identifiers = ("version",)
    _attributes = ()
    _children = {}

    version: str

    uuid: Optional[UUID] = None


class Device(DiffSyncModel):
    """DiffSync model for Meraki devices."""

    _modelname = "device"
    _identifiers = ("name",)
    _attributes = ("controller_group", "notes", "serial", "status", "role", "model", "network", "tenant", "version")
    _children = {"port": "ports"}

    name: str
    controller_group: Optional[str] = None
    notes: Optional[str] = None
    serial: Optional[str] = None
    status: Optional[str] = None
    role: Optional[str] = None
    model: Optional[str] = None
    network: str
    tenant: Optional[str] = None
    version: Optional[str] = None
    ports: List["Port"] = []

    uuid: Optional[UUID] = None


class Port(DiffSyncModel):
    """DiffSync model for Meraki device ports."""

    _modelname = "port"
    _identifiers = ("name", "device")
    _attributes = ("management", "enabled", "port_type", "port_status", "tagging")
    _children = {}

    name: str
    device: str
    management: bool
    enabled: bool
    port_type: str
    port_status: str
    tagging: bool

    uuid: Optional[UUID] = None


class Prefix(DiffSyncModel):
    """DiffSync model for Meraki Prefixes."""

    _modelname = "prefix"
    _identifiers = ("prefix", "namespace")
    _attributes = ("tenant",)
    _children = {}

    prefix: str
    namespace: str
    tenant: Optional[str] = None

    uuid: Optional[UUID] = None


class PrefixLocation(DiffSyncModel):
    """DiffSync model for tracking Locations assigned to Prefixes in Meraki."""

    _modelname = "prefixlocation"
    _identifiers = ("prefix", "location")
    _attributes = ()
    _children = {}

    prefix: str
    location: str

    uuid: Optional[UUID] = None


class IPAddress(DiffSyncModel):
    """DiffSync model for Meraki IP Addresses."""

    _modelname = "ipaddress"
    _identifiers = ("host", "tenant")
    _attributes = ("mask_length", "prefix")
    _children = {}

    host: str
    mask_length: int
    prefix: str
    tenant: Optional[str] = None

    uuid: Optional[UUID] = None


class IPAssignment(DiffSyncModel):
    """DiffSync model for Citrix ADM tracking IPAddress on particular Device interfaces."""

    _modelname = "ipassignment"
    _identifiers = ("address", "device", "namespace", "port")
    _attributes = ("primary",)
    _children = {}

    address: str
    namespace: str
    device: str
    port: str
    primary: bool

    uuid: Optional[UUID] = None
