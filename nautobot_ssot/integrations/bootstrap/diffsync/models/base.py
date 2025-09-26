"""DiffSyncModel subclasses for Nautobot-to-bootstrap data sync."""

import datetime
from typing import List, Optional, Union
from uuid import UUID

from diffsync import DiffSyncModel


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

    uuid: Optional[UUID] = None


class SecretsGroup(DiffSyncModel):
    """DiffSync model for Bootstrap SecretsGroups."""

    _modelname = "secrets_group"
    _identifiers = ("name",)
    _attributes = ("secrets", "system_of_record")
    _children = {}

    name: str
    secrets: List["dict"] = []
    system_of_record: str

    uuid: Optional[UUID] = None


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
    secrets_group: Optional[str] = None
    provided_contents: List[str] = []
    system_of_record: str

    uuid: Optional[UUID] = None


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

    uuid: Optional[UUID] = None


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

    uuid: Optional[UUID] = None


class Tag(DiffSyncModel):
    """DiffSync model for Bootstrap Tags."""

    _modelname = "tag"
    _identifiers = ("name",)
    _attributes = ("color", "content_types", "description", "system_of_record")
    _children = {}

    name: str
    color: str
    content_types: List[str] = []
    description: str
    system_of_record: str

    uuid: Optional[UUID] = None


class GraphQLQuery(DiffSyncModel):
    """DiffSync Model for Bootstrap GraphQLQueries."""

    _modelname = "graph_ql_query"
    _identifiers = ("name",)
    _attributes = ("query",)
    _children = {}

    name: str
    query: str

    uuid: Optional[UUID] = None


# TODO Merge SoftwareVersion and Software once no longer need to support DLM < 2.0.0 and Nautobot < 2.3.0
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
    alias: Optional[str] = None
    release_date: Optional[datetime.date] = None
    eos_date: Optional[datetime.date] = None
    documentation_url: Optional[str] = None
    long_term_support: bool
    pre_release: bool
    tags: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


# TODO Merge SoftwareVersion and Software once no longer need to support DLM < 2.0.0 and Nautobot < 2.3.0
class SoftwareVersion(DiffSyncModel):
    """DiffSync Model for Bootstrap SoftwareVersion."""

    _modelname = "software_version"
    _identifiers = (
        "version",
        "platform",
    )
    _attributes = (
        "alias",
        "release_date",
        "eos_date",
        "status",
        "long_term_support",
        "pre_release",
        "documentation_url",
        "tags",
        "system_of_record",
    )
    _children = {}

    version: str
    platform: str
    status: str
    alias: Optional[str] = None
    release_date: Optional[datetime.date] = None
    eos_date: Optional[datetime.date] = None
    documentation_url: Optional[str] = None
    long_term_support: bool
    pre_release: bool
    tags: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


# TODO Merge SoftwareImage and SoftwareImageFile once no longer need to support DLM < 2.0.0 and Nautobot < 2.3.0
class SoftwareImage(DiffSyncModel):
    """DiffSync Model for Bootstrap SoftwareImage."""

    _modelname = "software_version"
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
    download_url: Optional[str] = None
    image_file_checksum: Optional[str] = None
    hashing_algorithm: str
    default_image: bool
    tags: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


# TODO Merge SoftwareImage and SoftwareImageFile once no longer need to support DLM < 2.0.0 and Nautobot < 2.3.0
class SoftwareImageFile(DiffSyncModel):
    """DiffSync Model for Bootstrap SoftwareImageFile."""

    _modelname = "software_image_file"
    _identifiers = ("software_version", "image_file_name")
    _attributes = (
        "platform",
        "status",
        "file_size",
        "device_types",
        "download_url",
        "image_file_checksum",
        "hashing_algorithm",
        "default_image",
        "tags",
        "system_of_record",
    )
    _children = {}

    platform: str
    status: str
    file_size: Optional[int] = None
    device_types: Optional[List[str]] = None
    software_version: str
    image_file_name: str
    download_url: Optional[str] = None
    image_file_checksum: Optional[str] = None
    hashing_algorithm: Optional[str] = None
    default_image: bool
    tags: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


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

    devices: Optional[List[str]] = None
    device_types: Optional[List[str]] = None
    device_roles: Optional[List[str]] = None
    inventory_items: Optional[List[str]] = None
    object_tags: Optional[List[str]] = None
    software: str
    platform: str
    software_version: str
    valid_since: Optional[datetime.date] = None
    valid_until: Optional[datetime.date] = None
    preferred_version: bool
    tags: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


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
    parent: Optional[str] = None
    description: Optional[str] = None
    system_of_record: str

    uuid: Optional[UUID] = None


class Tenant(DiffSyncModel):
    """DiffSync Model for Bootstrap Tenant."""

    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("description", "tenant_group", "tags", "system_of_record")
    _children = {}

    name: str
    tenant_group: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


class Role(DiffSyncModel):
    """DiffSync Model for Bootstrap Role."""

    _modelname = "role"
    _identifiers = ("name",)
    _attributes = (
        "weight",
        "description",
        "color",
        "content_types",
        "system_of_record",
    )
    _children = {}

    name: str
    weight: Optional[int] = None
    description: Optional[str] = None
    color: Optional[str] = None
    content_types: List[str] = []
    system_of_record: str

    uuid: Optional[UUID] = None


class Team(DiffSyncModel):
    """DiffSync Model for Bootstrap Team."""

    _modelname = "team"
    _identifiers = ("name",)
    _attributes = ("phone", "email", "address", "contacts", "system_of_record")
    _children = {}

    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    contacts: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


class Contact(DiffSyncModel):
    """DiffSync Model for Bootstrap Contact."""

    _modelname = "contact"
    _identifiers = ("name",)
    _attributes = ("phone", "email", "address", "teams", "system_of_record")
    _children = {}

    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    teams: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


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
    description: Optional[str] = None
    system_of_record: str

    uuid: Optional[UUID] = None


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
    manufacturer: Optional[str] = None
    network_driver: Optional[str] = None
    napalm_driver: Optional[str] = None
    napalm_arguments: Optional[dict] = None
    description: Optional[str] = None
    system_of_record: str

    uuid: Optional[UUID] = None


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
    parent: Optional[str] = None
    nestable: Optional[bool] = None
    description: Optional[str] = None
    content_types: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


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
    parent: Optional[str] = None
    status: Optional[str] = None
    facility: Optional[str] = None
    asn: Optional[int] = None
    time_zone: Optional[str] = None
    description: Optional[str] = None
    tenant: Optional[str] = None
    physical_address: Optional[str] = None
    shipping_address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    tags: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


class Provider(DiffSyncModel):
    """DiffSync model for Bootstrap Provider."""

    _modelname = "provider"
    _identifiers = ("name",)
    _attributes = (
        "asn",
        "account_number",
        "portal_url",
        "noc_contact",
        "admin_contact",
        "tags",
        "system_of_record",
    )
    _children = {}

    name: str
    asn: Optional[int] = None
    account_number: Optional[str] = None
    portal_url: Optional[str] = None
    noc_contact: Optional[str] = None
    admin_contact: Optional[str] = None
    tags: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


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
    description: Optional[str] = None
    comments: Optional[str] = None
    tags: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


class CircuitType(DiffSyncModel):
    """DiffSync model for Bootstrap CircuitType."""

    _modelname = "circuit_type"
    _identifiers = ("name",)
    _attributes = ("description", "system_of_record")
    _children = {}

    name: str
    description: Optional[str] = None
    system_of_record: str

    uuid: Optional[UUID] = None


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
    date_installed: Optional[datetime.date] = None
    commit_rate_kbps: Optional[int] = None
    description: Optional[str] = None
    tenant: Optional[str] = None
    tags: Optional[List[str]] = None
    terminations: Optional[List["Circuit"]] = []
    system_of_record: Optional[str] = None

    uuid: Optional[UUID] = None


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
    location: Optional[str] = None
    provider_network: Optional[str] = None
    port_speed_kbps: Optional[int] = None
    upstream_speed_kbps: Optional[int] = None
    cross_connect_id: Optional[str] = None
    patch_panel_or_ports: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


class Namespace(DiffSyncModel):
    """DiffSync model for Bootstrap Namespace."""

    _modelname = "namespace"
    _identifiers = ("name",)
    _attributes = ("description", "location", "system_of_record")
    _children = {}

    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    system_of_record: str

    uuid: Optional[UUID] = None


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
    description: Optional[str] = None
    system_of_record: str

    uuid: Optional[UUID] = None


class VLANGroup(DiffSyncModel):
    """DiffSync model for Bootstrap VLANGroup."""

    _modelname = "vlan_group"
    _identifiers = ("name",)
    _attributes = ("location", "description", "system_of_record")
    _children = {}

    name: str
    location: Optional[str] = None
    description: Optional[str] = None
    system_of_record: str

    uuid: Optional[UUID] = None


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
    vlan_group: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    role: Optional[str] = None
    locations: Optional[List[str]] = None
    tenant: Optional[str] = None
    tags: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


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
    namespace: Optional[str] = None
    route_distinguisher: Optional[str] = None
    description: Optional[str] = None
    tenant: Optional[str] = None
    tags: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


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
    prefix_type: Optional[str] = None
    status: Optional[str] = None
    role: Optional[str] = None
    rir: Optional[str] = None
    date_allocated: Optional[datetime.datetime] = None
    description: Optional[str] = None
    vrfs: Optional[List[str]] = None
    locations: Optional[List[str]] = None
    vlan: Optional[str] = None
    tenant: Optional[str] = None
    tags: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


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

    uuid: Optional[UUID] = None


class ScheduledJob(DiffSyncModel):
    """DiffSync model for Scheduled Jobs."""

    _modelname = "scheduled_job"
    _identifiers = ("name",)
    _attributes = (
        "job_model",
        "user",
        "interval",
        "start_time",
        "crontab",
        "job_vars",
        "profile",
        "approval_required",
        "task_queue",
        "enabled",
    )
    _children = {}

    name: str
    job_model: str
    user: str
    interval: str
    start_time: str
    crontab: str
    job_vars: dict
    profile: bool = False
    approval_required: bool = False
    task_queue: Optional[str] = None
    enabled: Optional[bool] = True

    uuid: Optional[UUID] = None


class CustomField(DiffSyncModel):
    """DiffSync model for Custom Fields."""

    _modelname = "custom_field"
    _identifiers = ("label",)
    _attributes = (
        "description",
        "required",
        "content_types",
        "type",
        "grouping",
        "weight",
        "default",
        "filter_logic",
        "advanced_ui",
        "validation_minimum",
        "validation_maximum",
        "validation_regex",
        "custom_field_choices",
    )
    _children = {}

    label: str
    description: str
    type: str
    grouping: str
    weight: int
    filter_logic: str
    advanced_ui: bool
    required: bool = False
    content_types: List[str] = []
    custom_field_choices: Optional[list] = []
    validation_minimum: Optional[int] = None
    validation_maximum: Optional[int] = None
    validation_regex: Optional[str] = None
    default: Optional[Union[str, bool, dict]] = None

    uuid: Optional[UUID] = None


class ExternalIntegration(DiffSyncModel):
    """DiffSync model for External Integrations."""

    _modelname = "external_integration"
    _identifiers = ("name",)
    _attributes = (
        "remote_url",
        "timeout",
        "verify_ssl",
        "secrets_group",
        "headers",
        "http_method",
        "ca_file_path",
        "extra_config",
        "tags",
        "system_of_record",
    )
    _children = {}

    name: str
    remote_url: str
    timeout: int
    verify_ssl: bool = True
    secrets_group: Optional[str] = None
    headers: Optional[dict] = None
    http_method: Optional[str] = None
    ca_file_path: Optional[str] = None
    extra_config: Optional[dict] = None
    tags: Optional[List[str]] = None
    system_of_record: str

    uuid: Optional[UUID] = None


Circuit.model_rebuild()
CircuitTermination.model_rebuild()
