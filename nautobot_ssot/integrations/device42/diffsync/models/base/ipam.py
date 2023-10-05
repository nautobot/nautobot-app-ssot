"""Base IPAM subclasses DiffSyncModel for nautobot_ssot_device42 data sync."""

from typing import List, Optional
from uuid import UUID

from diffsync import DiffSyncModel


class VRFGroup(DiffSyncModel):
    """Base VRFGroup model."""

    _modelname = "vrf"
    _identifiers = ("name",)
    _attributes = ("description", "tags", "custom_fields")
    _children = {}
    name: str
    description: Optional[str]
    tags: Optional[List[str]]
    custom_fields: Optional[dict]
    uuid: Optional[UUID]


class Subnet(DiffSyncModel):
    """Base Subnet model."""

    _modelname = "subnet"
    _identifiers = (
        "network",
        "mask_bits",
        "vrf",
    )
    _attributes = ("description", "tags", "custom_fields")
    _children = {}
    network: str
    mask_bits: int
    description: Optional[str]
    vrf: Optional[str]
    tags: Optional[List[str]]
    custom_fields: Optional[dict]
    uuid: Optional[UUID]


class IPAddress(DiffSyncModel):
    """Base IP Address model."""

    _modelname = "ipaddr"
    _identifiers = ("address", "subnet")
    _attributes = ("namespace", "available", "label", "device", "interface", "primary", "tags", "custom_fields")
    _children = {}

    address: str
    subnet: str
    namespace: str
    available: bool
    label: Optional[str]
    device: Optional[str]
    interface: Optional[str]
    primary: Optional[bool]
    tags: Optional[List[str]]
    custom_fields: Optional[dict]
    uuid: Optional[UUID]


class VLAN(DiffSyncModel):
    """Base VLAN model."""

    _modelname = "vlan"
    _identifiers = (
        "vlan_id",
        "building",
    )
    _attributes = ("name", "description", "custom_fields", "tags")
    _children = {}

    name: str
    vlan_id: int
    description: Optional[str]
    building: Optional[str]
    custom_fields: Optional[dict]
    tags: Optional[List[str]]
    uuid: Optional[UUID]
