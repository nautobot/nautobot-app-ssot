"""Base Shared Models for Infoblox integration with SSoT app."""

import uuid
from typing import Optional
from diffsync import DiffSyncModel


class Namespace(DiffSyncModel):
    """Namespace model for DiffSync."""

    _modelname = "namespace"
    _identifiers = ("name",)
    _attributes = ("ext_attrs",)

    name: str
    ext_attrs: Optional[dict]
    pk: Optional[uuid.UUID] = None


class Network(DiffSyncModel):
    """Network model for DiffSync."""

    _modelname = "prefix"
    _identifiers = ("network", "namespace")
    _attributes = ("description", "network_type", "ext_attrs", "vlans", "ranges")

    network: str
    namespace: str
    description: Optional[str]
    network_type: Optional[str]
    ext_attrs: Optional[dict]
    vlans: Optional[dict]
    ranges: Optional[list] = []
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
    _identifiers = ("address", "prefix", "prefix_length", "namespace")
    _attributes = (
        "description",
        "dns_name",
        "status",
        "ip_addr_type",
        "ext_attrs",
        "has_host_record",
        "has_a_record",
        "has_ptr_record",
        "has_fixed_address",
        "mac_address",
    )

    address: str
    dns_name: str
    prefix: str
    prefix_length: int
    namespace: str
    status: Optional[str]
    ip_addr_type: Optional[str]
    description: Optional[str]
    ext_attrs: Optional[dict]
    has_a_record: bool = False
    has_host_record: bool = False
    has_ptr_record: bool = False
    has_fixed_address: bool = False
    mac_address: Optional[str]

    pk: Optional[uuid.UUID] = None
    a_record_ref: Optional[str] = None
    host_record_ref: Optional[str] = None
    ptr_record_ref: Optional[str] = None
    fixed_address_ref: Optional[str] = None
    fixed_address_type: Optional[str] = None
