# pylint: disable=too-many-lines
"""Setup/Create Nautobot objects for use in unit testing."""

import json
import os
from unittest.mock import MagicMock

import pytz
import yaml
from django.contrib.contenttypes.models import ContentType
from django.utils.text import slugify
from nautobot.circuits.models import (
    Circuit,
    CircuitTermination,
    CircuitType,
    Provider,
    ProviderNetwork,
)
from nautobot.dcim.models import (
    Device,
    DeviceType,
    InventoryItem,
    Location,
    LocationType,
    Manufacturer,
    Platform,
)
from nautobot.extras.models import (
    ComputedField,
    Contact,
    CustomField,
    DynamicGroup,
    ExternalIntegration,
    GitRepository,
    GraphQLQuery,
    Job,
    JobResult,
    Role,
    ScheduledJob,
    Secret,
    SecretsGroup,
    SecretsGroupAssociation,
    Status,
    Tag,
    Team,
)
from nautobot.ipam.models import RIR, VLAN, VRF, Namespace, Prefix, VLANGroup
from nautobot.tenancy.models import Tenant, TenantGroup
from nautobot.users.models import User

from nautobot_ssot.integrations.bootstrap.diffsync.adapters.bootstrap import (
    BootstrapAdapter,
)
from nautobot_ssot.integrations.bootstrap.diffsync.adapters.nautobot import (
    NautobotAdapter,
)
from nautobot_ssot.integrations.bootstrap.jobs import BootstrapDataSource
from nautobot_ssot.integrations.bootstrap.utils import get_scheduled_start_time
from nautobot_ssot.utils import core_supports_softwareversion, dlm_supports_softwarelcm, validate_dlm_installed

if core_supports_softwareversion():
    from nautobot.dcim.models import SoftwareImageFile, SoftwareVersion  # pylint: disable=ungrouped-imports

    if validate_dlm_installed():
        from nautobot_device_lifecycle_mgmt.models import ValidatedSoftwareLCM

if dlm_supports_softwarelcm():
    from nautobot_device_lifecycle_mgmt.models import SoftwareImageLCM, SoftwareLCM, ValidatedSoftwareLCM


def load_yaml(path):
    """Load a yaml file."""
    with open(path, encoding="utf-8") as file:
        return yaml.safe_load(file.read())


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


FIXTURES_DIR = os.path.join("./nautobot_ssot/integrations/bootstrap/fixtures")
DEVELOP_YAML_SETTINGS = load_yaml(os.path.join(FIXTURES_DIR, "develop.yml"))

TESTS_FIXTURES_DIR = os.path.join("./nautobot_ssot/tests/bootstrap/fixtures")
GLOBAL_YAML_SETTINGS = load_yaml(os.path.join(FIXTURES_DIR, "global_settings.yml"))
GLOBAL_JSON_SETTINGS = load_json(os.path.join(TESTS_FIXTURES_DIR, "global_settings.json"))

MODELS_TO_SYNC = [
    "tenant_group",
    "tenant",
    "role",
    "manufacturer",
    "platform",
    "location_type",
    "location",
    "team",
    "contact",
    "provider",
    "provider_network",
    "circuit_type",
    "circuit",
    "circuit_termination",
    "secret",
    "secrets_group",
    "git_repository",
    "dynamic_group",
    "computed_field",
    "custom_field",
    "tag",
    "graph_ql_query",
    "software",  # For Nautobot <2.3.0
    "software_version",  # For Nautobot >=2.3.0
    "software_image",  # For Nautobot <2.3.0
    "software_image_file",  # For Nautobot >=2.3.0
    "validated_software",
    "namespace",
    "rir",
    "vlan_group",
    "vlan",
    "vrf",
    "prefix",
    "scheduled_job",
    "external_integration",
]

MODELS_TO_TEST = [
    "tenant_group",
    "tenant",
    "role",
    "manufacturer",
    "platform",
    "location_type",
    "location",
    "team",
    "contact",
    "provider",
    "provider_network",
    "circuit_type",
    "circuit",
    "circuit_termination",
    "secret",
    "secrets_group",
    "git_repository",
    "dynamic_group",
    "computed_field",
    "custom_field",
    "tag",
    "graph_ql_query",
    "namespace",
    "rir",
    "vlan_group",
    "vlan",
    "vrf",
    "prefix",
    "scheduled_job",
    "external_integration",
]


def is_valid_timezone(timezone):
    """Return whether timezone passed is a valid timezone in pytz."""
    try:
        pytz.timezone(timezone)
        return True
    except pytz.UnknownTimeZoneError:
        return False


class PrefixInfo:
    """Definition for a prefix object"""

    def __init__(self, namespace, prefix_type, role, rir, vlan, tenant):  # pylint: disable=too-many-arguments
        self.namespace = namespace
        self.prefix_type = prefix_type
        self.role = role
        self.rir = rir
        self.vlan = vlan
        self.tenant = tenant


class NautobotTestSetup:
    """Setup basic database information to be used in other tests."""

    def __init__(self):
        self.job = BootstrapDataSource()
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )
        self.nb_adapter = NautobotAdapter(job=self.job, sync=None)
        self.nb_adapter.job = MagicMock()
        self.nb_adapter.job.logger.info = MagicMock()
        self.bs_adapter = BootstrapAdapter(job=self.job, sync=None)
        self.bs_adapter.job = MagicMock()
        self.bs_adapter.job.logger.info = MagicMock()
        self.status_active = None
        self._initialize_data()

    def _initialize_data(self):
        self._setup_tags()
        self._setup_status()
        self._setup_locations()
        self._setup_tenant_groups()
        self._setup_tenants()
        self._setup_roles()
        self._setup_teams()
        self._setup_contacts()
        self._setup_providers()
        self._setup_provider_networks()
        self._setup_circuit_types()
        self._setup_circuits()
        self._setup_circuit_terminations()
        self._setup_manufacturers()
        self._setup_platforms()
        self._setup_device_types_and_devices()
        self._setup_inventory_items()
        self._setup_secrets_and_groups()
        self._setup_computed_fields()
        self._setup_custom_fields()
        self._setup_graphql_queries()
        self._setup_git_repositories()
        self._setup_dynamic_groups()
        self._setup_namespaces()
        self._setup_rirs()
        self._setup_vlan_groups()
        self._setup_vlans()
        self._setup_vrfs()
        self._setup_prefixes()
        self._setup_external_integrations()
        if dlm_supports_softwarelcm():
            self._setup_software_and_images()
        self._setup_validated_software()
        self._setup_scheduled_job()

    def _setup_tags(self):
        for _tag in GLOBAL_YAML_SETTINGS["tag"]:
            _content_types = []
            for _con_type in _tag["content_types"]:
                _content_types.append(
                    ContentType.objects.get(app_label=_con_type.split(".")[0], model=_con_type.split(".")[1])
                )
            _new_tag = Tag.objects.create(
                name=_tag["name"],
                description=_tag["description"],
                color=_tag["color"] if not None else "9e9e9e",
            )
            _new_tag.custom_field_data["system_of_record"] = "Bootstrap"
            _new_tag.validated_save()
            _new_tag.content_types.set(_content_types)
            _new_tag.validated_save()
            _new_tag.refresh_from_db()

    def _setup_status(self):
        _statuses = ["Reserved"]
        self.status_active, _ = Status.objects.get_or_create(name="Active")
        self.status_active.save()
        _content_types = [
            "circuits.circuit",
            "dcim.location",
            "dcim.device",
            "ipam.prefix",
            "ipam.namespace",
            "ipam.vrf",
            "ipam.vlan",
            "ipam.ipaddress",
        ]
        for _content_type in _content_types:
            _con_type = ContentType.objects.get(
                app_label=_content_type.split(".", maxsplit=1)[0],
                model=_content_type.split(".")[1],
            )
            self.status_active.content_types.add(_con_type)
        self.status_active.refresh_from_db()
        for _status in _statuses:
            status, _ = Status.objects.get_or_create(name=_status)
            for _content_type in _content_types:
                _con_type = ContentType.objects.get(
                    app_label=_content_type.split(".", maxsplit=1)[0],
                    model=_content_type.split(".")[1],
                )
                status.content_types.add(_con_type)
            status.validated_save()

    def _setup_locations(self):
        """Set up location types and locations."""

        # First, ensure location types are created
        location_types_data = GLOBAL_YAML_SETTINGS.get("location_type", [])
        for loc_type_data in location_types_data:
            location_type = self._get_or_create_location_type(loc_type_data)
            self._set_location_type_content_types(location_type, loc_type_data["content_types"])

        locations_data = GLOBAL_YAML_SETTINGS.get("location", [])
        for location_data in locations_data:
            location_type = LocationType.objects.get(name=location_data["location_type"])
            parent_location = None
            tenant = None
            tags = []

            status = Status.objects.get(name=location_data["status"])

            if location_data["parent"]:
                parent_location = Location.objects.get(name=location_data["parent"])

            if location_data["tenant"]:
                tenant = Tenant.objects.get(name=location_data["tenant"])

            if location_data["tags"]:
                tags = [Tag.objects.get(name=tag) for tag in location_data["tags"]]

            location, created = Location.objects.get_or_create(
                name=location_data["name"],
                location_type=location_type,
                defaults={
                    "parent": parent_location,
                    "status": status,
                    "facility": location_data.get("facility", ""),
                    "asn": location_data.get("asn"),
                    "time_zone": location_data.get("time_zone", ""),
                    "description": location_data.get("description", ""),
                    "tenant": tenant,
                    "physical_address": location_data.get("physical_address", ""),
                    "shipping_address": location_data.get("shipping_address", ""),
                    "latitude": location_data.get("latitude"),
                    "longitude": location_data.get("longitude"),
                    "contact_name": location_data.get("contact_name", ""),
                    "contact_phone": location_data.get("contact_phone", ""),
                    "contact_email": location_data.get("contact_email", ""),
                    "tags": tags,
                },
            )
            if created:
                location.validated_save()

    def _get_or_create_location_type(self, location_type_data):
        """Get or create a LocationType based on the provided data."""
        parent = self._get_location_type_parent(location_type_data["parent"])
        try:
            return LocationType.objects.get(name=location_type_data["name"], parent=parent)
        except LocationType.DoesNotExist:
            return LocationType.objects.create(
                name=location_type_data["name"],
                parent=parent,
                nestable=location_type_data.get("nestable"),
                description=location_type_data["description"],
            )

    def _get_location_type_parent(self, parent_name):
        """Retrieve the parent LocationType if it exists."""
        if parent_name:
            try:
                return LocationType.objects.get(name=parent_name)
            except LocationType.DoesNotExist:
                self.job.logger.warning(f"Parent LocationType '{parent_name}' does not exist.")
                return None
        return None

    def _set_location_type_content_types(self, location_type, content_types):
        """Set the content types for a LocationType."""
        content_type_objects = [
            ContentType.objects.get(app_label=ct.split(".")[0], model=ct.split(".")[1]) for ct in content_types
        ]
        location_type.content_types.set(content_type_objects)
        location_type.custom_field_data["system_of_record"] = "Bootstrap"
        location_type.save()

    def _setup_tenant_groups(self):
        _tenant_groups = GLOBAL_YAML_SETTINGS.get("tenant_group", [])
        for _tenant_group in _tenant_groups:
            if _tenant_group["parent"]:
                _parent = TenantGroup.objects.get(name=_tenant_group["parent"])
                _tenant_group = TenantGroup.objects.create(name=_tenant_group["name"], parent=_parent)
            else:
                _tenant_group = TenantGroup.objects.create(name=_tenant_group["name"])
            _tenant_group.custom_field_data["system_of_record"] = "Bootstrap"
            _tenant_group.validated_save()
            _tenant_group.refresh_from_db()

    def _setup_tenants(self):
        _tenants = GLOBAL_YAML_SETTINGS.get("tenant", [])
        for _ten in _tenants:
            _tenant_group = None
            if _ten["tenant_group"]:
                _tenant_group = TenantGroup.objects.get(name=_ten["tenant_group"])
            _tenant = Tenant.objects.create(
                name=_ten["name"],
                description=_ten["description"],
                tenant_group=_tenant_group,
            )
            _tenant.custom_field_data["system_of_record"] = "Bootstrap"
            if _ten["tags"]:
                for _tag in _ten["tags"]:
                    _tenant.tags.add(Tag.objects.get(name=_tag))
            _tenant.validated_save()
            _tenant.refresh_from_db()

    def _setup_roles(self):
        _con_types = []
        _roles = GLOBAL_YAML_SETTINGS["role"]
        # _roles.remove(["Administrative", "Anycast", "Billing", "CARP", "GLBP", "HSRP", "Loopback", "On Site", ])
        for _role in _roles:
            for _type in _role["content_types"]:
                _con_types.append(ContentType.objects.get(app_label=_type.split(".")[0], model=_type.split(".")[1]))
            _r, created = Role.objects.get_or_create(
                name=_role["name"],
                color=_role["color"],
                description=_role["description"],
            )
            if created:
                _r.content_types.set(_con_types)
                _r.custom_field_data["system_of_record"] = "Bootstrap"
                _r.validated_save()
            _con_types.clear()
        # if DLM 3.x is installed, remove the added roles
        if not dlm_supports_softwarelcm():
            for dlm_v3_role in ["DLM Primary", "DLM Tier 1", "DLM Tier 2", "DLM Tier 3", "DLM Owner", "DLM Unassigned"]:
                try:
                    Role.objects.get(name=dlm_v3_role).delete()
                except Role.DoesNotExist:
                    pass

    def _setup_teams(self):
        for _team in GLOBAL_YAML_SETTINGS["team"]:
            team = Team.objects.create(
                name=_team["name"],
                phone=_team["phone"],
                email=_team["email"],
                address=_team["address"],
            )
            team.custom_field_data["system_of_record"] = "Bootstrap"
            team.validated_save()

    def _setup_contacts(self):
        for _contact in GLOBAL_YAML_SETTINGS["contact"]:
            contact = Contact.objects.create(
                name=_contact["name"],
                phone=_contact["phone"],
                email=_contact["email"],
                address=_contact["address"],
            )
            contact.validated_save()
            for _team in _contact["teams"]:
                contact.teams.add(Team.objects.get(name=_team))
            contact.custom_field_data["system_of_record"] = "Bootstrap"
            contact.validated_save()

    def _setup_providers(self):
        for _provider in GLOBAL_YAML_SETTINGS["provider"]:
            provider = Provider.objects.create(
                name=_provider["name"],
                asn=_provider["asn"],
                account=_provider["account_number"],
                portal_url=_provider["portal_url"],
                noc_contact=_provider["noc_contact"],
                admin_contact=_provider["admin_contact"],
            )
            provider.validated_save()
            for _tag in _provider["tags"]:
                _t = Tag.objects.get(name=_tag)
                provider.tags.append(_t)
            provider.custom_field_data["system_of_record"] = "Bootstrap"
            provider.validated_save()

    def _setup_provider_networks(self):
        for _provider_network in GLOBAL_YAML_SETTINGS["provider_network"]:
            _provider = Provider.objects.get(name=_provider_network["provider"])
            provider_network = ProviderNetwork.objects.create(
                name=_provider_network["name"],
                provider=_provider,
                description=_provider_network["description"],
                comments=_provider_network["comments"],
            )
            provider_network.validated_save()
            for _tag in _provider_network["tags"]:
                _t = Tag.objects.get(name=_tag)
                provider_network.tags.append(_t)
            provider_network.custom_field_data["system_of_record"] = "Bootstrap"
            provider_network.validated_save()

    def _setup_circuit_types(self):
        for _circuit_type in GLOBAL_YAML_SETTINGS["circuit_type"]:
            circuit_type = CircuitType(
                name=_circuit_type["name"],
                description=_circuit_type["description"],
            )
            circuit_type.custom_field_data["system_of_record"] = "Bootstrap"
            circuit_type.validated_save()

    def _setup_circuits(self):
        for _circuit in GLOBAL_YAML_SETTINGS["circuit"]:
            _provider = Provider.objects.get(name=_circuit["provider"])
            _circuit_type = CircuitType.objects.get(name=_circuit["circuit_type"])
            _status = Status.objects.get(name=_circuit["status"])
            _tenant = None
            if _circuit["tenant"]:
                if _circuit["tenant"] is not None:
                    _tenant = Tenant.objects.get(name=_circuit["tenant"])
            circuit = Circuit(
                cid=_circuit["circuit_id"],
                provider=_provider,
                circuit_type=_circuit_type,
                status=_status,
                commit_rate=_circuit["commit_rate_kbps"],
                description=_circuit["description"],
                tenant=_tenant,
            )
            circuit.validated_save()
            for _tag in _circuit["tags"]:
                _t = Tag.objects.get(name=_tag)
                circuit.tags.append(_t)
            circuit.custom_field_data["system_of_record"] = "Bootstrap"
            circuit.validated_save()

    def _setup_circuit_terminations(self):
        for _circuit_termination in GLOBAL_YAML_SETTINGS["circuit_termination"]:
            _name_parts = _circuit_termination["name"].split("__", 2)
            _circuit_id = _name_parts[0]
            _provider_name = _name_parts[1]
            _term_side = _name_parts[2]
            _provider = Provider.objects.get(name=_provider_name)
            _circuit = Circuit.objects.get(cid=_circuit_id, provider=_provider)

            if _circuit_termination["termination_type"] == "Provider Network":
                _provider_network = ProviderNetwork.objects.get(name=_circuit_termination["provider_network"])
                circuit_termination = CircuitTermination.objects.create(
                    provider_network=_provider_network,
                    circuit=_circuit,
                    term_side=_term_side,
                    xconnect_id=_circuit_termination["cross_connect_id"],
                    pp_info=_circuit_termination["patch_panel_or_ports"],
                    description=_circuit_termination["description"],
                    upstream_speed=_circuit_termination["upstream_speed_kbps"],
                    port_speed=_circuit_termination["port_speed_kbps"],
                )
            if _circuit_termination["termination_type"] == "Location":
                _location = Location.objects.get(name=_circuit_termination["location"])
                circuit_termination = CircuitTermination.objects.create(
                    location=_location,
                    circuit=_circuit,
                    term_side=_term_side,
                    xconnect_id=_circuit_termination["cross_connect_id"],
                    pp_info=_circuit_termination["patch_panel_or_ports"],
                    description=_circuit_termination["description"],
                    upstream_speed=_circuit_termination["upstream_speed_kbps"],
                    port_speed=_circuit_termination["port_speed_kbps"],
                )
                circuit_termination.custom_field_data["system_of_record"] = "Bootstrap"
                circuit_termination.validated_save()
                if _circuit_termination["tags"]:
                    for _tag in _circuit_termination["tags"]:
                        circuit_termination.tags.add(Tag.objects.get(name=_tag))

    def _setup_namespaces(self):
        for _namespace in GLOBAL_YAML_SETTINGS["namespace"]:
            _location = None
            if _namespace["location"]:
                _location = Location.objects.get(name=_namespace["location"])
            namespace, _ = Namespace.objects.get_or_create(
                name=_namespace["name"],
                location=_location,
            )
            namespace.description = _namespace["description"]
            namespace.custom_field_data["system_of_record"] = "Bootstrap"
            namespace.validated_save()

    def _setup_rirs(self):
        for _rir in GLOBAL_YAML_SETTINGS["rir"]:
            rir, _ = RIR.objects.get_or_create(
                name=_rir["name"],
            )
            rir.is_private = _rir["private"]
            rir.description = _rir["description"]
            rir.custom_field_data["system_of_record"] = "Bootstrap"
            rir.validated_save()

    def _setup_vlan_groups(self):
        for _vlan_group in GLOBAL_YAML_SETTINGS["vlan_group"]:
            _location = None
            if _vlan_group["location"]:
                _location = Location.objects.get(name=_vlan_group["location"])
            vlan_group, _ = VLANGroup.objects.get_or_create(name=_vlan_group["name"], location=_location)
            vlan_group.description = _vlan_group["description"]
            vlan_group.custom_field_data["system_of_record"] = "Bootstrap"
            vlan_group.validated_save()

    def _setup_vlans(self):
        for _vlan in GLOBAL_YAML_SETTINGS["vlan"]:
            _role = None
            _locations = []
            _vlan_group = None
            _tenant = None
            _tags = []
            _status = self.status_active
            if _vlan["status"] and _vlan["status"] != "Active":
                _status = Status.objects.get(name=_vlan["status"])
            if _vlan["role"]:
                _role = Role.objects.get(name=_vlan["role"])
            if _vlan["locations"]:
                for _l in _vlan["locations"]:
                    _locations.append(Location.objects.get(name=_l))
            if _vlan["vlan_group"]:
                _vlan_group = VLANGroup.objects.get(name=_vlan["vlan_group"])
            if _vlan["tenant"]:
                _tenant = Tenant.objects.get(name=_vlan["tenant"])
            if _vlan["tags"]:
                for _t in _vlan["tags"]:
                    _tags.append(Tag.objects.get(name=_t))
            vlan, _ = VLAN.objects.get_or_create(
                vid=_vlan["vid"],
                name=_vlan["name"],
                vlan_group=_vlan_group,
                status=_status,
            )
            vlan.role = _role
            vlan.locations.set(_locations)
            vlan.tenant = _tenant
            vlan.description = _vlan["description"]
            vlan.custom_field_data["system_of_record"] = "Bootstrap"
            vlan.validated_save()
            vlan.tags.set(_tags)

    def _setup_vrfs(self):
        for _vrf in GLOBAL_YAML_SETTINGS["vrf"]:
            _namespace = None
            _tenant = None
            _tags = []
            if _vrf["namespace"]:
                _namespace = Namespace.objects.get(name=_vrf["namespace"])
            if _vrf["tenant"]:
                _tenant = Tenant.objects.get(name=_vrf["tenant"])
            if _vrf["tags"]:
                for _t in _vrf["tags"]:
                    _tags.append(Tag.objects.get(name=_t))
            vrf, _ = VRF.objects.get_or_create(
                name=_vrf["name"],
                namespace=_namespace,
            )
            vrf.rd = _vrf["route_distinguisher"]
            vrf.description = _vrf["description"]
            vrf.tenant = _tenant
            vrf.custom_field_data["system_of_record"] = "Bootstrap"
            vrf.tags.set(_tags)
            vrf.validated_save()

    def _setup_prefixes(self):
        for prefix_data in GLOBAL_YAML_SETTINGS["prefix"]:
            namespace = self._get_namespace(prefix_data)
            prefix_type = self._get_prefix_type(prefix_data)
            role = self._get_role(prefix_data)
            rir = self._get_rir(prefix_data)
            vrfs = self._get_vrfs(prefix_data)
            locations = self._get_locations(prefix_data)
            vlan = self._get_vlan(prefix_data)
            tenant = self._get_tenant(prefix_data)
            tags = self._get_prefix_tags(prefix_data)

            prefix_info = PrefixInfo(namespace, prefix_type, role, rir, vlan, tenant)
            prefix = self._get_or_create_prefix(prefix_data, prefix_info)
            self._update_prefix(prefix, locations, vrfs, tags)

    def _get_namespace(self, prefix_data):
        if prefix_data["namespace"] and prefix_data["namespace"] != "Global":
            return Namespace.objects.get(name=prefix_data["namespace"])
        return Namespace.objects.get(name="Global")

    def _get_prefix_type(self, prefix_data):
        if prefix_data["prefix_type"] and prefix_data["prefix_type"] != "network":
            return prefix_data["prefix_type"]
        return "network"

    def _get_role(self, prefix_data):
        if prefix_data["role"]:
            return Role.objects.get(name=prefix_data["role"])
        return None

    def _get_rir(self, prefix_data):
        if prefix_data["rir"]:
            return RIR.objects.get(name=prefix_data["rir"])
        return None

    def _get_vrfs(self, prefix_data):
        vrfs = []
        if prefix_data["vrfs"]:
            for vrf in prefix_data["vrfs"]:
                namespace = Namespace.objects.get(name=vrf.split("__")[1])
                vrfs.append(VRF.objects.get(name=vrf.split("__")[0], namespace=namespace))
        return vrfs

    def _get_locations(self, prefix_data):
        locations = []
        if prefix_data["locations"]:
            for loc in prefix_data["locations"]:
                locations.append(Location.objects.get(name=loc))
        return locations

    def _get_vlan(self, prefix_data):
        if prefix_data["vlan"]:
            name, vid, group = prefix_data["vlan"].split("__", 2)
            vlan_group = VLANGroup.objects.get(name=group) if group else None
            return VLAN.objects.get(name=name, vid=vid, vlan_group=vlan_group)
        return None

    def _get_tenant(self, prefix_data):
        if prefix_data["tenant"]:
            return Tenant.objects.get(name=prefix_data["tenant"])
        return None

    def _get_prefix_tags(self, prefix_data):
        tags = []
        if prefix_data["tags"]:
            for tag in prefix_data["tags"]:
                tags.append(Tag.objects.get(name=tag))
        return tags

    def _get_or_create_prefix(self, prefix_data, prefix_info):
        try:
            return Prefix.objects.get(
                network=prefix_data["network"].split("/")[0],
                prefix_length=prefix_data["network"].split("/")[1],
                namespace=prefix_info.namespace,
                type=prefix_info.prefix_type,
            )
        except Prefix.DoesNotExist:
            return Prefix.objects.create(
                network=prefix_data["network"].split("/")[0],
                prefix_length=prefix_data["network"].split("/")[1],
                namespace=prefix_info.namespace,
                type=prefix_info.prefix_type,
                status=Status.objects.get(name=prefix_data["status"]),
                role=prefix_info.role,
                rir=prefix_info.rir,
                date_allocated=prefix_data["date_allocated"],
                description=prefix_data["description"],
                vlan=prefix_info.vlan,
                tenant=prefix_info.tenant,
            )

    def _update_prefix(self, prefix, locations, vrfs, tags):
        prefix.custom_field_data["system_of_record"] = "Bootstrap"
        prefix.validated_save()
        for loc in locations:
            prefix.locations.add(loc)
        for vrf in vrfs:
            prefix.vrfs.add(vrf)
        for tag in tags:
            prefix.tags.add(tag)
        prefix.validated_save()

    def _setup_manufacturers(self):
        for _manufacturer in GLOBAL_YAML_SETTINGS["manufacturer"]:
            _manufac = Manufacturer.objects.create(name=_manufacturer["name"], description=_manufacturer["description"])
            _manufac.custom_field_data["system_of_record"] = "Bootstrap"
            _manufac.validated_save()

    def _setup_platforms(self):
        for _platform in GLOBAL_YAML_SETTINGS["platform"]:
            _manufac = None
            if _platform["manufacturer"]:
                _manufac = Manufacturer.objects.get(name=_platform["manufacturer"])
            _platf = Platform.objects.create(
                name=_platform["name"],
                manufacturer=_manufac,
                description=_platform["description"],
                network_driver=_platform["network_driver"],
                napalm_args=_platform["napalm_arguments"],
                napalm_driver=_platform["napalm_driver"],
            )
            _platf.custom_field_data["system_of_record"] = "Bootstrap"
            _platf.validated_save()

    def _setup_device_types_and_devices(self):
        _device_types = [
            {"model": "WS3850-24P", "manufacturer": "Cisco"},
            {"model": "PA-820", "manufacturer": "Palo Alto Networks"},
        ]
        _devices = [
            {
                "name": "Switch1",
                "manufacturer": "Cisco",
                "platform": "cisco_ios",
                "location": "Atlanta",
                "device_type": "WS3850-24P",
                "role": "Switch",
            },
            {
                "name": "Firewall1",
                "manufacturer": "Palo Alto Networks",
                "platform": "paloalto_panos",
                "location": "Atlanta",
                "device_type": "PA-820",
                "role": "Firewall",
            },
        ]

        for _dev_type in _device_types:
            _manufacturer = Manufacturer.objects.get(name=_dev_type["manufacturer"])
            _dev_type = DeviceType.objects.create(model=_dev_type["model"], manufacturer=_manufacturer)
            _dev_type.custom_field_data["system_of_record"] = "Bootstrap"
            _dev_type.validated_save()

        for _dev in _devices:
            _manufacturer = Manufacturer.objects.get(name=_dev["manufacturer"])
            _platform = Platform.objects.get(name=_dev["platform"])
            _dev_type = DeviceType.objects.get(model=_dev["device_type"])
            _role = Role.objects.get(name=_dev["role"])
            _site = Location.objects.get(name=_dev["location"])
            _device = Device.objects.create(
                name=_dev["name"],
                platform=_platform,
                device_type=_dev_type,
                status=self.status_active,
                role=_role,
                location=_site,
            )
            _device.custom_field_data["system_of_record"] = "Bootstrap"
            _device.save()
            _device.refresh_from_db()

    def _setup_inventory_items(self):
        _inventory_items = [{"name": "sfp-module", "device": "Switch1", "manufacturer": "Cisco"}]
        for _inv_item in _inventory_items:
            _dev = Device.objects.get(name=_inv_item["device"])
            _manufacturer = Manufacturer.objects.get(name=_inv_item["manufacturer"])
            _inventory_item = InventoryItem.objects.create(
                name=_inv_item["name"], device=_dev, manufacturer=_manufacturer
            )
            _inventory_item.custom_field_data["system_of_record"] = "Bootstrap"
            _inventory_item.save()
            _inventory_item.refresh_from_db()

    def _setup_secrets_and_groups(self):
        for _sec in GLOBAL_YAML_SETTINGS["secret"]:
            _secret = Secret.objects.create(
                name=_sec["name"],
                provider=_sec["provider"],
                parameters=_sec["parameters"],
            )
            _secret.custom_field_data["system_of_record"] = "Bootstrap"
            _secret.save()
            _secret.refresh_from_db()

        for _sec_group in GLOBAL_YAML_SETTINGS["secrets_group"]:
            _secrets_group = SecretsGroup.objects.create(name=_sec_group["name"])
            _secrets_group.custom_field_data["system_of_record"] = "Bootstrap"
            _secrets_group.validated_save()
            _secrets_group.refresh_from_db()
            for _sec in _sec_group["secrets"]:
                _sga = SecretsGroupAssociation.objects.create(
                    secrets_group=_secrets_group,
                    secret=Secret.objects.get(name=_sec["name"]),
                    access_type=_sec["access_type"],
                    secret_type=_sec["secret_type"],
                )
                _sga.validated_save()
                _sga.refresh_from_db()

    def _setup_computed_fields(self):
        for _comp_field in GLOBAL_YAML_SETTINGS["computed_field"]:
            _content_type = ContentType.objects.get(
                app_label=_comp_field["content_type"].split(".")[0],
                model=_comp_field["content_type"].split(".")[1],
            )
            _computed_field = ComputedField.objects.create(
                label=_comp_field["label"],
                content_type=_content_type,
                template=_comp_field["template"],
            )
            _computed_field.save()
            _computed_field.refresh_from_db()

    def _setup_custom_fields(self):
        for _cust_field in GLOBAL_YAML_SETTINGS["custom_field"]:
            _content_types = []
            for _content_type in _cust_field["content_types"]:
                _content_types.append(
                    ContentType.objects.get(
                        app_label=_content_type.split(".")[0],
                        model=_content_type.split(".")[1],
                    )
                )

            _cust_field = CustomField.objects.create(
                label=_cust_field["label"],
                type=_cust_field["type"],
                description=_cust_field["description"],
            )
            _cust_field.content_types.set(_content_types)
            _cust_field.save()
            _cust_field.refresh_from_db()

    def _setup_graphql_queries(self):
        for _gql_query in GLOBAL_YAML_SETTINGS["graph_ql_query"]:
            _qglq = GraphQLQuery.objects.create(name=_gql_query["name"], query=_gql_query["query"])
            _qglq.save()
            _qglq.refresh_from_db()

    def _setup_git_repositories(self):
        for _repo in GLOBAL_YAML_SETTINGS["git_repository"]:
            if _repo.get("branch"):
                _git_branch = _repo["branch"]
            else:
                _git_branch = DEVELOP_YAML_SETTINGS["git_branch"]
            _secrets_group = None
            if _repo.get("secrets_group_name"):
                _secrets_group = SecretsGroup.objects.get(name=_repo["secrets_group_name"])
            _git_repo = GitRepository.objects.create(
                name=_repo["name"],
                slug=slugify(_repo["name"]),
                remote_url=_repo["url"],
                branch=_git_branch,
                secrets_group=_secrets_group,
                provided_contents=_repo["provided_data_type"],
            )
            _git_repo.custom_field_data["system_of_record"] = "Bootstrap"
            _git_repo.validated_save()

    def _setup_dynamic_groups(self):
        for _group in GLOBAL_YAML_SETTINGS["dynamic_group"]:
            _content_type = ContentType.objects.get(
                app_label=_group["content_type"].split(".")[0],
                model=_group["content_type"].split(".")[1],
            )
            _dynamic_group = DynamicGroup.objects.create(
                name=_group["name"],
                content_type=_content_type,
                filter=json.loads(_group["filter"]),
                description=_group["description"],
            )
            _dynamic_group.custom_field_data["system_of_record"] = "Bootstrap"
            _dynamic_group.validated_save()
            _dynamic_group.refresh_from_db()

    def _setup_software_and_images(self):
        """Set up software and software images for testing."""
        # Handle software versions for both old and new Nautobot versions
        if core_supports_softwareversion():
            # For Nautobot >=2.3.0
            for _software in GLOBAL_YAML_SETTINGS["software_version"]:
                _tags = []
                for _tag in _software["tags"]:
                    _tags.append(Tag.objects.get(name=_tag))
                _platform = Platform.objects.get(name=_software["platform"])
                _soft = SoftwareVersion.objects.create(
                    version=_software["version"],
                    platform=_platform,
                    status=self.status_active,
                    alias=_software["alias"],
                    end_of_support_date=_software["eos_date"],
                    documentation_url=_software["documentation_url"],
                    long_term_support=_software["long_term_support"],
                    pre_release=_software["pre_release"],
                )
                _soft.custom_field_data["system_of_record"] = "Bootstrap"
                _soft.validated_save()
                _soft.refresh_from_db()

            # For Nautobot >=2.3.0
            for _software_image in GLOBAL_YAML_SETTINGS["software_image_file"]:
                _tags = []
                for _tag in _software_image["tags"]:
                    _tags.append(Tag.objects.get(name=_tag))
                _platform = Platform.objects.get(name=_software_image["platform"])
                _software = SoftwareVersion.objects.get(
                    version=_software_image["software_version"].split(" - ")[1], platform=_platform
                )
                _soft_image = SoftwareImageFile.objects.create(
                    software_version=_software,
                    image_file_name=_software_image["image_file_name"],
                    image_file_checksum=_software_image["image_file_checksum"],
                    image_file_size=_software_image["file_size"],
                    hashing_algorithm=_software_image["hashing_algorithm"],
                    download_url=_software_image["download_url"],
                    default_image=_software_image["default_image"],
                    status=self.status_active,
                )
                _soft_image.custom_field_data["system_of_record"] = "Bootstrap"
                _soft_image.validated_save()
                _soft_image.refresh_from_db()
        else:
            # For Nautobot <2.3.0
            for _software in GLOBAL_YAML_SETTINGS["software"]:
                _tags = []
                for _tag in _software["tags"]:
                    _tags.append(Tag.objects.get(name=_tag))
                _platform = Platform.objects.get(name=_software["platform"])
                _soft = SoftwareLCM.objects.create(
                    version=_software["version"],
                    alias=_software["alias"],
                    device_platform=_platform,
                    end_of_support=_software["eos_date"],
                    long_term_support=_software["long_term_support"],
                    pre_release=_software["pre_release"],
                    documentation_url=_software["documentation_url"],
                    tags=_tags,
                )
                _soft.custom_field_data["system_of_record"] = "Bootstrap"
                _soft.validated_save()
                _soft.refresh_from_db()

            # For Nautobot <2.3.0
            for _software_image in GLOBAL_YAML_SETTINGS["software_image"]:
                _tags = []
                for _tag in _software_image["tags"]:
                    _tags.append(Tag.objects.get(name=_tag))
                _platform = Platform.objects.get(name=_software_image["platform"])
                _software = SoftwareLCM.objects.get(
                    version=_software_image["software_version"], device_platform=_platform
                )
                _soft_image = SoftwareImageLCM.objects.create(
                    software=_software,
                    image_file_name=_software_image["file_name"],
                    image_file_checksum=_software_image["image_file_checksum"],
                    hashing_algorithm=_software_image["hashing_algorithm"],
                    download_url=_software_image["download_url"],
                    default_image=_software_image["default_image"],
                    tags=_tags,
                )
                _soft_image.custom_field_data["system_of_record"] = "Bootstrap"
                _soft_image.validated_save()
                _soft_image.refresh_from_db()

    def _setup_validated_software(self):
        for validated_software_data in GLOBAL_YAML_SETTINGS["validated_software"]:
            tags = self._get_validated_software_tags(validated_software_data["tags"])
            devices = self._get_devices(validated_software_data["devices"])
            device_types = self._get_device_types(validated_software_data["device_types"])
            device_roles = self._get_device_roles(validated_software_data["device_roles"])
            inventory_items = self._get_inventory_items(validated_software_data["inventory_items"])
            object_tags = self._get_object_tags(validated_software_data["object_tags"])

            software = self._get_software(validated_software_data["software"])

            validated_software = ValidatedSoftwareLCM.objects.create(
                software=software,
                start=validated_software_data["valid_since"],
                end=validated_software_data["valid_until"],
                preferred=validated_software_data["preferred_version"],
                tags=tags,
            )
            validated_software.custom_field_data["system_of_record"] = "Bootstrap"
            validated_software.validated_save()

            self._set_validated_software_relations(
                validated_software,
                devices,
                device_types,
                device_roles,
                inventory_items,
                object_tags,
            )

    def _setup_scheduled_job(self):
        admin = User.objects.create(
            username="admin",
            password="admin",
            is_superuser=True,
            is_staff=True,
        )
        job = Job.objects.get(name="Export Object List")

        for scheduled_job in GLOBAL_YAML_SETTINGS["scheduled_job"]:
            # Parse the start_time to preserve timezone info
            start_time = get_scheduled_start_time(scheduled_job["start_time"])
            scheduled_job = ScheduledJob(
                name=scheduled_job["name"],
                task=job.class_path,
                interval=scheduled_job["interval"],
                start_time=start_time,
                job_model=job,
                user=admin,
                kwargs={},
            )
            scheduled_job.validated_save()

    def _setup_external_integrations(self):
        """Set up external integrations for testing."""
        for _ext_int in GLOBAL_YAML_SETTINGS["external_integration"]:
            if _ext_int.get("secrets_group"):
                _secrets_group = SecretsGroup.objects.get(name=_ext_int["secrets_group"])
            _nb_ext_int = ExternalIntegration.objects.create(
                name=_ext_int["name"],
                remote_url=_ext_int["remote_url"],
                verify_ssl=_ext_int["verify_ssl"],
                secrets_group=_secrets_group,
                http_method=_ext_int["http_method"],
                ca_file_path=_ext_int["ca_file_path"],
                timeout=_ext_int["timeout"],
                headers=_ext_int["headers"],
                extra_config=_ext_int["extra_config"],
            )
            _nb_ext_int.custom_field_data["system_of_record"] = "Bootstrap"
            if _ext_int["tags"]:
                for _tag in _ext_int["tags"]:
                    _nb_ext_int.tags.add(Tag.objects.get(name=_tag))
            _nb_ext_int.save()
            _nb_ext_int.refresh_from_db()

    def _get_validated_software_tags(self, tag_names):
        return [Tag.objects.get(name=tag_name) for tag_name in tag_names]

    def _get_devices(self, device_names):
        return [Device.objects.get(name=device_name) for device_name in device_names]

    def _get_device_types(self, device_type_names):
        return [DeviceType.objects.get(model=device_type_name) for device_type_name in device_type_names]

    def _get_device_roles(self, device_role_names):
        return [Role.objects.get(name=device_role_name) for device_role_name in device_role_names]

    def _get_inventory_items(self, inventory_item_names):
        return [InventoryItem.objects.get(name=inventory_item_name) for inventory_item_name in inventory_item_names]

    def _get_object_tags(self, object_tag_names):
        return [Tag.objects.get(name=object_tag_name) for object_tag_name in object_tag_names]

    def _get_software(self, software_name):
        platform_name, software_version = software_name.split(" - ")
        platform = Platform.objects.get(name=platform_name)
        if core_supports_softwareversion():
            software = SoftwareVersion.objects.get_or_create(
                version=software_version, platform=platform, status=self.status_active
            )[0]
        elif dlm_supports_softwarelcm():
            software = SoftwareLCM.objects.get_or_create(version=software_version, device_platform=platform)[0]
        return software

    def _set_validated_software_relations(
        self,
        validated_software,
        devices,
        device_types,
        device_roles,
        inventory_items,
        object_tags,
    ):  # pylint: disable=too-many-arguments
        validated_software.devices.set(devices)
        validated_software.device_types.set(device_types)
        validated_software.device_roles.set(device_roles)
        validated_software.inventory_items.set(inventory_items)
        validated_software.object_tags.set(object_tags)


KEYS_TO_NORMALIZE = {
    "parent",
    "nestable",
    "tenant",
    "tenant_group",
    "terminations",
    "provider_network",
    "upstream_speed_kbps",
    "location",
}
