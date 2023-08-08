"""DiffSyncModel subclasses for Nautobot-to-AristaCV data sync."""
from uuid import UUID
from diffsync import DiffSyncModel
from diffsync.enum import DiffSyncModelFlags
from typing import List, Optional


class Device(DiffSyncModel):
    """Device Model."""

    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "device_model",
        "serial",
        "status",
        "version",
    )
    _children = {"port": "ports"}

    name: str
    device_model: str
    serial: str
    status: str
    version: Optional[str]
    ports: List["Port"] = list()
    uuid: Optional[UUID]


class Port(DiffSyncModel):
    """Port Model."""

    _modelname = "port"
    _identifiers = (
        "name",
        "device",
    )
    _attributes = (
        "description",
        "mac_addr",
        "enabled",
        "mode",
        "mtu",
        "port_type",
        "status",
    )
    _children = {}

    name: str
    device: str
    description: Optional[str]
    mac_addr: str
    enabled: bool
    mode: str
    mtu: Optional[int]
    port_type: str
    status: str
    uuid: Optional[UUID]


class IPAddress(DiffSyncModel):
    """IPAddress Model."""

    model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _modelname = "ipaddr"
    _identifiers = (
        "address",
        "device",
        "interface",
    )
    _attributes = ()
    _children = {}

    address: str
    device: str
    interface: str
    uuid: Optional[UUID]


class CustomField(DiffSyncModel):
    """Custom Field model."""

    _modelname = "cf"
    _identifiers = ("name", "device_name")
    _attributes = ("value",)
    _children = {}

    name: str
    value: str
    device_name: str
