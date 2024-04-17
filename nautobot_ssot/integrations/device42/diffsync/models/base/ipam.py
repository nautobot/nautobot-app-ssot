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
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[dict] = None
    uuid: Optional[UUID] = None


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
    description: Optional[str] = None
    vrf: Optional[str] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[dict] = None
    uuid: Optional[UUID] = None


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
    label: Optional[str] = None
    device: Optional[str] = None
    interface: Optional[str] = None
    primary: Optional[bool] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[dict] = None
    uuid: Optional[UUID] = None


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
    description: Optional[str] = None
    building: Optional[str] = None
    custom_fields: Optional[dict] = None
    tags: Optional[List[str]] = None
    uuid: Optional[UUID] = None
