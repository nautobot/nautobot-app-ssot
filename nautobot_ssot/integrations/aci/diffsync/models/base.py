"""Base Shared Models for Cisco ACI integration with SSoT app."""

from typing import List, Optional

from diffsync import DiffSyncModel


class Tenant(DiffSyncModel):
    """Tenant model for DiffSync."""

    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("description", "comments", "site_tag", "msite_tag")

    name: str
    description: Optional[str] = None
    comments: Optional[str] = None
    site_tag: str
    msite_tag: bool


class Vrf(DiffSyncModel):
    """VRF model for DiffSync."""

    _modelname = "vrf"
    _identifiers = ("name", "tenant")
    _attributes = ("description", "namespace", "site_tag")

    name: str
    tenant: str
    description: Optional[str] = None
    namespace: str
    site_tag: str


class DeviceType(DiffSyncModel):
    """DeviceType model for DiffSync."""

    _modelname = "device_type"
    _identifiers = (
        "model",
        "part_nbr",
    )
    _attributes = (
        "manufacturer",
        "comments",
        "u_height",
    )
    _children = {
        "interface_template": "interface_templates",
    }

    model: str
    manufacturer: str
    part_nbr: str
    comments: Optional[str] = None
    u_height: Optional[int] = None

    interface_templates: List["InterfaceTemplate"] = []


class DeviceRole(DiffSyncModel):
    """DeviceRole model for DiffSync."""

    _modelname = "device_role"
    _identifiers = ("name",)
    _attributes = ("description",)

    name: str
    description: Optional[str] = None


class Device(DiffSyncModel):
    """Device model for DiffSync."""

    _modelname = "device"
    _identifiers = (
        "name",
        "site",
    )
    _attributes = (
        "device_role",
        "device_type",
        "serial",
        "comments",
        "node_id",
        "pod_id",
        "site_tag",
        "controller_group",
    )
    _children = {
        "interface": "interfaces",
    }

    name: str
    device_type: str
    device_role: str
    serial: str
    site: str
    comments: Optional[str]
    interfaces: List["Interface"] = []
    node_id: Optional[int]
    pod_id: Optional[int]
    site_tag: str
    controller_group: str


class InterfaceTemplate(DiffSyncModel):
    """InterfaceTemplate model for DiffSync."""

    _modelname = "interface_template"
    _identifiers = (
        "device_type",
        "name",
        "type",
    )
    _attributes = ("u_height", "mgmt_only", "site_tag")

    name: str
    device_type: str
    type: str
    u_height: Optional[int] = None
    mgmt_only: Optional[bool] = None
    site_tag: str


class IPAddress(DiffSyncModel):
    """IPAddress model for DiffSync."""

    _modelname = "ip_address"
    _identifiers = (
        "address",
        "site",
        "namespace",
        "tenant",
    )
    _attributes = ("prefix", "status", "description", "device", "interface", "site_tag")

    address: str
    prefix: str
    status: str
    site: str
    namespace: str
    description: Optional[str] = None
    device: Optional[str] = None
    interface: Optional[str] = None
    tenant: Optional[str] = None
    site_tag: str


class Prefix(DiffSyncModel):
    """Prefix model for DiffSync."""

    _modelname = "prefix"
    _identifiers = (
        "prefix",
        "site",
        "vrf",
        "tenant",
    )
    _attributes = ("namespace", "status", "description", "vrf_tenant", "site_tag")

    prefix: str
    namespace: str
    status: str
    site: str
    tenant: Optional[str]
    description: Optional[str]
    vrf: Optional[str]
    vrf_tenant: Optional[str]
    site_tag: str


class Interface(DiffSyncModel):
    """Interface model for DiffSync."""

    _modelname = "interface"
    _identifiers = (
        "name",
        "device",
        "site",
    )
    _attributes = ("description", "gbic_sn", "gbic_vendor", "gbic_type", "gbic_model", "state", "type", "site_tag")

    name: str
    device: str
    site: str
    description: Optional[str]
    gbic_sn: Optional[str]
    gbic_vendor: Optional[str]
    gbic_type: Optional[str]
    gbic_model: Optional[str]
    state: Optional[str]
    type: str
    site_tag: str
