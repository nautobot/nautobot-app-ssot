"""DiffSyncModel subclasses for Nautobot-to-bootstrap data sync."""
from typing import Optional, List
from uuid import UUID
from diffsync import DiffSyncModel
import datetime


class Secret(DiffSyncModel):
    """DiffSync model for Bootstrap Secrets."""

    _modelname = "secret"
    _identifiers = ("name",)
    _attributes = ("provider", "parameters", "system_of_record")
    _children = {}

    name: str
    provider: str
    parameters: dict
    system_of_record: str

    uuid: Optional[UUID]


class SecretsGroup(DiffSyncModel):
    """DiffSync model for Bootstrap SecretsGroups."""

    _modelname = "secrets_group"
    _identifiers = ("name",)
    _attributes = ("secrets", "system_of_record")
    _children = {}

    name: str
    secrets: List["dict"] = list()
    system_of_record: str

    uuid: Optional[UUID]


class GitRepository(DiffSyncModel):
    """DiffSync model for Bootstrap GitRepositories."""

    _modelname = "git_repository"
    _identifiers = ("name",)
    _attributes = (
        "url",
        "branch",
        "secrets_group",
        "provided_contents",
        "system_of_record",
    )
    _children = {}

    name: str
    url: str
    branch: str
    secrets_group: Optional[str]
    provided_contents: List[str]
    system_of_record: str

    uuid: Optional[UUID]


class DynamicGroup(DiffSyncModel):
    """DiffSync model for Bootstrap DynamicGroups."""

    _modelname = "dynamic_group"
    _identifiers = ("name", "content_type")
    _attributes = ("dynamic_filter", "description", "system_of_record")
    _children = {}

    name: str
    content_type: str
    dynamic_filter: dict
    description: str
    system_of_record: str

    uuid: Optional[UUID]


class ComputedField(DiffSyncModel):
    """DiffSync model for Bootstrap ComputedFields."""

    _modelname = "computed_field"
    _identifiers = ("label",)
    _attributes = (
        "content_type",
        "template",
    )
    _children = {}

    label: str
    content_type: str
    template: str

    uuid: Optional[UUID]


class Tag(DiffSyncModel):
    """DiffSync model for Bootstrap Tags."""

    _modelname = "tag"
    _identifiers = ("name",)
    _attributes = ("color", "content_types", "description", "system_of_record")
    _children = {}

    name: str
    color: str
    content_types: List[str]
    description: str
    system_of_record: str

    uuid: Optional[UUID]


class GraphQLQuery(DiffSyncModel):
    """DiffSync Model for Bootstrap GraphQLQueries."""

    _modelname = "graph_ql_query"
    _identifiers = ("name",)
    _attributes = ("query",)
    _children = {}

    name: str
    query: str

    uuid: Optional[UUID]


class Software(DiffSyncModel):
    """DiffSync Model for Bootstrap Software."""

    _modelname = "software"
    _identifiers = (
        "version",
        "platform",
    )
    _attributes = (
        "alias",
        "release_date",
        "eos_date",
        "long_term_support",
        "pre_release",
        "documentation_url",
        "tags",
        "system_of_record",
    )
    _children = {}

    version: str
    platform: str
    alias: Optional[str]
    release_date: Optional[datetime.date]
    eos_date: Optional[datetime.date]
    documentation_url: Optional[str]
    long_term_support: bool
    pre_release: bool
    tags: Optional[List[str]]
    system_of_record: str

    uuid: Optional[UUID]


class SoftwareImage(DiffSyncModel):
    """DiffSync Model for Bootstrap SoftwareImage."""

    _modelname = "software_image"
    _identifiers = ("software",)
    _attributes = (
        "platform",
        "software_version",
        "file_name",
        "download_url",
        "image_file_checksum",
        "hashing_algorithm",
        "default_image",
        "tags",
        "system_of_record",
    )
    _children = {}

    software: str
    platform: str
    software_version: str
    file_name: str
    download_url: Optional[str]
    image_file_checksum: Optional[str]
    hashing_algorithm: str
    default_image: bool
    tags: Optional[List[str]]
    system_of_record: str

    uuid: Optional[UUID]


class ValidatedSoftware(DiffSyncModel):
    """DiffSync Model for Bootstrap ValidatedSoftware."""

    _modelname = "validated_software"
    _identifiers = ("software", "valid_since", "valid_until")
    _attributes = (
        "devices",
        "device_types",
        "device_roles",
        "inventory_items",
        "object_tags",
        "preferred_version",
        "tags",
        "platform",
        "software_version",
        "system_of_record",
    )
    _children = {}

    devices: Optional[list[str]]
    device_types: Optional[list[str]]
    device_roles: Optional[list[str]]
    inventory_items: Optional[list[str]]
    object_tags: Optional[list[str]]
    software: str
    platform: str
    software_version: str
    valid_since: Optional[datetime.date]
    valid_until: Optional[datetime.date]
    preferred_version: bool
    tags: Optional[List[str]]
    system_of_record: str

    uuid: Optional[UUID]


class TenantGroup(DiffSyncModel):
    """DiffSync Model for Bootstrap TenantGroup."""

    _modelname = "tenant_group"
    _identifiers = ("name", "parent")
    _attributes = (
        "description",
        "system_of_record",
    )
    _children = {}

    name: str
    parent: Optional[str]
    description: Optional[str]
    system_of_record: str

    uuid: Optional[UUID]


class Tenant(DiffSyncModel):
    """DiffSync Model for Bootstrap Tenant."""

    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("description", "tenant_group", "tags", "system_of_record")
    _children = {}

    name: str
    tenant_group: Optional[str]
    description: Optional[str]
    tags: Optional[List[str]]
    system_of_record: str

    uuid: Optional[UUID]


class Role(DiffSyncModel):
    """DiffSync Model for Bootstrap Role."""

    _modelname = "role"
    _identifiers = ("name",)
    _attributes = ("weight", "description", "color", "content_types", "system_of_record")
    _children = {}

    name: str
    weight: Optional[int]
    description: Optional[str]
    color: Optional[str]
    content_types: List[str]
    system_of_record: str

    uuid: Optional[UUID]


class Team(DiffSyncModel):
    """DiffSync Model for Bootstrap Team."""

    _modelname = "team"
    _identifiers = ("name",)
    _attributes = ("phone", "email", "address", "contacts", "system_of_record")
    _children = {}

    name: str
    phone: Optional[str]
    email: Optional[str]
    address: Optional[str]
    contacts: Optional[List[str]]
    system_of_record: str

    uuid: Optional[UUID]


class Contact(DiffSyncModel):
    """DiffSync Model for Bootstrap Contact."""

    _modelname = "contact"
    _identifiers = ("name",)
    _attributes = ("phone", "email", "address", "teams", "system_of_record")
    _children = {}

    name: str
    phone: Optional[str]
    email: Optional[str]
    address: Optional[str]
    teams: Optional[List[str]]
    system_of_record: str

    uuid: Optional[UUID]


class Manufacturer(DiffSyncModel):
    """DiffSync Model for Bootstrap Manufacturer."""

    _modelname = "manufacturer"
    _identifiers = ("name",)
    _attributes = (
        "description",
        "system_of_record",
    )
    _children = {}

    name: str
    description: Optional[str]
    system_of_record: str

    uuid: Optional[UUID]


class Platform(DiffSyncModel):
    """DiffSync Model for Bootstrap Platform."""

    _modelname = "platform"
    _identifiers = (
        "name",
        "manufacturer",
    )
    _attributes = (
        "network_driver",
        "napalm_driver",
        "napalm_arguments",
        "description",
        "system_of_record",
    )
    _children = {}

    name: str
    manufacturer: str
    network_driver: Optional[str]
    napalm_driver: Optional[str]
    napalm_arguments: Optional[dict]
    description: Optional[str]
    system_of_record: str

    uuid: Optional[UUID]


class LocationType(DiffSyncModel):
    """DiffSync Model for Bootstrap LocationType."""

    _modelname = "location_type"
    _identifiers = ("name",)
    _attributes = (
        "parent",
        "nestable",
        "description",
        "content_types",
        "system_of_record",
    )
    _children = {}

    name: str
    parent: Optional[str]
    nestable: Optional[bool]
    description: Optional[str]
    content_types: Optional[List[str]]
    system_of_record: str

    uuid: Optional[UUID]


class Location(DiffSyncModel):
    """DiffSync Model for Bootstrap Location."""

    _modelname = "location"
    _identifiers = (
        "name",
        "location_type",
    )
    _attributes = (
        "parent",
        "status",
        "facility",
        "asn",
        "time_zone",
        "description",
        "tenant",
        "physical_address",
        "shipping_address",
        "latitude",
        "longitude",
        "contact_name",
        "contact_phone",
        "contact_email",
        "tags",
        "system_of_record",
    )
    _children = {}

    name: str
    location_type: str
    parent: Optional[str]
    status: Optional[str]
    facility: Optional[str]
    asn: Optional[int]
    time_zone: Optional[str]
    description: Optional[str]
    tenant: Optional[str]
    physical_address: Optional[str]
    shipping_address: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    contact_name: Optional[str]
    contact_phone: Optional[str]
    contact_email: Optional[str]
    tags: Optional[List[str]]
    system_of_record: str

    uuid: Optional[UUID]


class Provider(DiffSyncModel):
    """DiffSync model for Bootstrap Provider."""

    _modelname = "provider"
    _identifiers = ("name",)
    _attributes = ("asn", "account_number", "portal_url", "noc_contact", "admin_contact", "tags", "system_of_record")
    _children = {}

    name: str
    asn: Optional[int]
    account_number: Optional[str]
    portal_url: Optional[str]
    noc_contact: Optional[str]
    admin_contact: Optional[str]
    tags: Optional[List[str]]
    system_of_record: str

    uuid: Optional[UUID]


class ProviderNetwork(DiffSyncModel):
    """DiffSync model for Bootstrap ProviderNetwork."""

    _modelname = "provider_network"
    _identifiers = (
        "name",
        "provider",
    )
    _attributes = ("description", "comments", "tags", "system_of_record")
    _children = {}

    name: str
    provider: str
    description: Optional[str]
    comments: Optional[str]
    tags: Optional[List[str]]
    system_of_record: str

    uuid: Optional[UUID]


class CircuitType(DiffSyncModel):
    """DiffSync model for Bootstrap CircuitType."""

    _modelname = "circuit_type"
    _identifiers = ("name",)
    _attributes = ("description", "system_of_record")
    _children = {}

    name: str
    description: Optional[str]
    system_of_record: str

    uuid: Optional[UUID]


class Circuit(DiffSyncModel):
    """DiffSync model for Bootstrap Circuit."""

    _modelname = "circuit"
    _identifiers = (
        "circuit_id",
        "provider",
    )
    _attributes = (
        "circuit_type",
        "status",
        "date_installed",
        "commit_rate_kbps",
        "description",
        "tenant",
        "tags",
        "system_of_record",
    )
    _children = {"circuit_termination": "terminations"}

    circuit_id: str
    provider: str
    circuit_type: str
    status: str
    date_installed: Optional[datetime.date]
    commit_rate_kbps: Optional[int]
    description: Optional[str]
    tenant: Optional[str]
    tags: Optional[List[str]]
    terminations: Optional[List["Circuit"]] = []
    system_of_record: Optional[str]

    uuid: Optional[UUID]


class CircuitTermination(DiffSyncModel):
    """DiffSync model for Bootstrap CircuitTermination."""

    _modelname = "circuit_termination"
    _identifiers = (
        "name",
        "termination_side",
        "circuit_id",
    )
    _attributes = (
        "termination_type",
        "location",
        "provider_network",
        "port_speed_kbps",
        "upstream_speed_kbps",
        "cross_connect_id",
        "patch_panel_or_ports",
        "description",
        "tags",
        "system_of_record",
    )
    _children = {}

    name: str
    termination_type: str
    termination_side: str
    circuit_id: str
    location: Optional[str]
    provider_network: Optional[str]
    port_speed_kbps: Optional[str]
    upstream_speed_kbps: Optional[str]
    cross_connect_id: Optional[str]
    patch_panel_or_ports: Optional[str]
    description: Optional[str]
    tags: Optional[List[str]]
    system_of_record: str

    uuid: Optional[UUID]


class Namespace(DiffSyncModel):
    """DiffSync model for Bootstrap Namespace."""

    _modelname = "namespace"
    _identifiers = ("name",)
    _attributes = ("description", "location", "system_of_record")
    _children = {}

    name: str
    description: Optional[str]
    location: Optional[str]
    system_of_record: str

    uuid: Optional[UUID]


class RiR(DiffSyncModel):
    """DiffSync model for Bootstrap RiR."""

    _modelname = "rir"
    _identifiers = [
        "name",
    ]
    _attributes = [
        "private",
        "description",
        "system_of_record",
    ]
    _children = {}

    name: str
    private: bool
    description: Optional[str]
    system_of_record: str

    uuid: Optional[UUID]


class VLANGroup(DiffSyncModel):
    """DiffSync model for Bootstrap VLANGroup."""

    _modelname = "vlan_group"
    _identifiers = ("name",)
    _attributes = ("location", "description", "system_of_record")
    _children = {}

    name: str
    location: Optional[str]
    description: Optional[str]
    system_of_record: str

    uuid: Optional[UUID]


class VLAN(DiffSyncModel):
    """DiffSync model for Bootstrap VLAN."""

    _modelname = "vlan"
    _identifiers = (
        "name",
        "vid",
        "vlan_group",
    )
    _attributes = (
        "description",
        "status",
        "role",
        "locations",
        "tenant",
        "tags",
        "system_of_record",
    )
    _children = {}

    name: str
    vid: int
    vlan_group: Optional[str]
    description: Optional[str]
    status: Optional[str]
    role: Optional[str]
    locations: Optional[List[str]]
    tenant: Optional[str]
    tags: Optional[List[str]]
    system_of_record: str

    uuid: Optional[UUID]


class VRF(DiffSyncModel):
    """DiffSync model for Bootstrap VRF."""

    _modelname = "vrf"
    _identifiers = (
        "name",
        "namespace",
    )
    _attributes = (
        "route_distinguisher",
        "description",
        "tenant",
        "tags",
        "system_of_record",
    )
    _children = {}

    name: str
    namespace: Optional[str]
    route_distinguisher: Optional[str]
    description: Optional[str]
    tenant: Optional[str]
    tags: Optional[List[str]]
    system_of_record: str

    uuid: Optional[UUID]


class Prefix(DiffSyncModel):
    """DiffSync model for Bootstrap Prefix."""

    _modelname = "prefix"
    _identifiers = (
        "network",
        "namespace",
    )
    _attributes = (
        "prefix_type",
        "status",
        "role",
        "rir",
        "date_allocated",
        "description",
        "vrfs",
        "locations",
        "vlan",
        "tenant",
        "tags",
        "system_of_record",
    )
    _children = {}

    network: str
    namespace: str
    prefix_type: Optional[str]
    status: Optional[str]
    role: Optional[str]
    rir: Optional[str]
    date_allocated: Optional[datetime.datetime]
    description: Optional[str]
    vrfs: Optional[List[str]]
    locations: Optional[List[str]]
    vlan: Optional[str]
    tenant: Optional[str]
    tags: Optional[List[str]]
    system_of_record: str

    uuid: Optional[UUID]


class SSoTJob(DiffSyncModel):
    """DiffSync model for Bootstrap SSoTJobs."""

    _modelname = "ssot-job"
    _identifiers = (
        "name",
        "schedule",
    )
    _attributes = ()
    _children = {}

    name: str
    schedule: str

    uuid: Optional[UUID]
