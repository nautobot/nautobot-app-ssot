"""Base Shared Models for Infoblox integration with SSoT plugin."""
import uuid
from typing import Optional
from diffsync import DiffSyncModel


class Network(DiffSyncModel):
    """Network model for DiffSync."""

    _modelname = "prefix"
    _identifiers = ("network",)
    _attributes = ("description", "status", "ext_attrs", "vlans")

    network: str
    description: Optional[str]
    status: Optional[str]
    ext_attrs: Optional[dict]
    vlans: Optional[dict]
    pk: Optional[uuid.UUID] = None


class VlanView(DiffSyncModel):
    """VLANView model for DiffSync."""

    _modelname = "vlangroup"
    _identifiers = ("name",)
    _attributes = ("description", "ext_attrs")

    name: str
    description: Optional[str]
    ext_attrs: Optional[dict]
    pk: Optional[uuid.UUID] = None


class Vlan(DiffSyncModel):
    """VLAN model for DiffSync."""

    _modelname = "vlan"
    _identifiers = ("vid", "name", "vlangroup")
    _attributes = ("description", "status", "ext_attrs")

    vid: int
    name: str
    status: str
    description: Optional[str]
    vlangroup: Optional[str]
    ext_attrs: Optional[dict]
    pk: Optional[uuid.UUID] = None


class IPAddress(DiffSyncModel):
    """IPAddress model for DiffSync."""

    _modelname = "ipaddress"
    _identifiers = ("address", "prefix", "prefix_length")
    _shortname = ("address",)
    _attributes = ("description", "dns_name", "status", "ext_attrs")

    address: str
    dns_name: str
    prefix: str
    prefix_length: int
    status: Optional[str]
    description: Optional[str]
    ext_attrs: Optional[dict]
    pk: Optional[uuid.UUID] = None


class Aggregate(DiffSyncModel):
    """Aggregate model for DiffSync."""

    _modelname = "aggregate"
    _identifiers = ("network",)
    _attributes = ("description", "ext_attrs")

    network: str
    description: Optional[str]
    ext_attrs: Optional[dict]
    pk: Optional[uuid.UUID] = None
