"""DiffSyncModel subclasses for Nautobot-to-AristaCV data sync."""

from typing import List, Optional, Union
from uuid import UUID

from diffsync import DiffSyncModel


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
    version: Optional[str] = None
    ports: List["Port"] = list()
    uuid: Optional[UUID] = None


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
    description: Optional[str] = None
    mac_addr: str
    enabled: bool
    mode: str
    mtu: Optional[int] = None
    port_type: str
    status: str
    uuid: Optional[UUID] = None


class Namespace(DiffSyncModel):
    """Namespace Model."""

    _modelname = "namespace"
    _identifiers = ("name",)
    _attributes = ()
    _children = {}

    name: str
    uuid: Optional[UUID] = None


class Prefix(DiffSyncModel):
    """Prefix Model."""

    _modelname = "prefix"
    _identifiers = ("prefix", "namespace")
    _attributes = ()
    _children = {}

    prefix: str
    namespace: str
    uuid: Optional[UUID] = None


class IPAddress(DiffSyncModel):
    """IPAddress Model."""

    _modelname = "ipaddr"
    _identifiers = (
        "address",
        "prefix",
        "namespace",
    )
    _attributes = ()
    _children = {}

    address: str
    prefix: str
    namespace: str
    uuid: Optional[UUID] = None


class IPAssignment(DiffSyncModel):
    """IPAssignment Model."""

    _modelname = "ipassignment"
    _identifiers = (
        "address",
        "namespace",
        "device",
        "interface",
    )
    _attributes = ("primary",)
    _children = {}

    address: str
    namespace: str
    device: str
    interface: str
    primary: bool
    uuid: Optional[UUID] = None


class CustomField(DiffSyncModel):
    """Custom Field model."""

    _modelname = "cf"
    _identifiers = ("name", "device_name")
    _attributes = ("value",)
    _children = {}

    name: str
    value: Union[str, bool]
    device_name: str
