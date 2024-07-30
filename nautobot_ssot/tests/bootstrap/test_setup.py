"""Setup/Create Nautobot objects for use in unit testing."""
# test_setup.py

import json
import yaml
import pytz
from unittest.mock import MagicMock
from django.contrib.contenttypes.models import ContentType
from django.utils.text import slugify
from nautobot.dcim.models import Device, DeviceType, InventoryItem, Location, LocationType, Manufacturer, Platform
from nautobot.extras.models import (
    ComputedField,
    DynamicGroup,
    GitRepository,
    GraphQLQuery,
    JobResult,
    Role,
    Secret,
    SecretsGroup,
    SecretsGroupAssociation,
    Status,
    Tag,
    Team,
    Contact,
)
from nautobot.circuits.models import Provider, ProviderNetwork, Circuit, CircuitType, CircuitTermination
from nautobot.ipam.models import Namespace, RIR, Prefix, VLAN, VLANGroup, VRF
from nautobot.tenancy.models import Tenant, TenantGroup
from nautobot_device_lifecycle_mgmt.models import SoftwareImageLCM, SoftwareLCM, ValidatedSoftwareLCM

from nautobot_ssot.integrations.bootstrap.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.integrations.bootstrap.diffsync.adapters.bootstrap import BootstrapAdapter
from nautobot_ssot.integrations.bootstrap.jobs import BootstrapDataSource


def load_yaml(path):
    """Load a yaml file."""
    with open(path, encoding="utf-8") as file:
        return yaml.safe_load(file.read())


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


GLOBAL_JSON_SETTINGS = load_json("./nautobot_ssot/tests/bootstrap/fixtures/global_settings.json")
GLOBAL_YAML_SETTINGS = load_yaml("./nautobot_ssot/tests/bootstrap/fixtures/global_settings.yml")
DEVELOP_YAML_SETTINGS = load_yaml("./nautobot_ssot/tests/bootstrap/fixtures/develop.yml")


def is_valid_timezone(tz):
    try:
        pytz.timezone(tz)
        return True
    except pytz.UnknownTimeZoneError:
        return False


class NautobotTestSetup:
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
        self._setup_manufacturers_and_platforms()
        self._setup_device_types_and_devices()
        self._setup_inventory_items()
        self._setup_secrets_and_groups()
        self._setup_computed_fields()
        self._setup_graphql_queries()
        self._setup_git_repositories()
        self._setup_dynamic_groups()
        self._setup_namespaces()
        self._setup_rirs()
        self._setup_vlan_groups()
        self._setup_vlans()
        self._setup_vrfs()
        self._setup_prefixes()
        self._setup_software_and_images()
        self._setup_validated_software()

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
                app_label=_content_type.split(".")[0], model=_content_type.split(".")[1]
            )
            self.status_active.content_types.add(_con_type)
        self.status_active.refresh_from_db()
        for _status in _statuses:
            status, _ = Status.objects.get_or_create(name=_status)
            for _content_type in _content_types:
                _con_type = ContentType.objects.get(
                    app_label=_content_type.split(".")[0], model=_content_type.split(".")[1]
                )
                status.content_types.add(_con_type)
            status.validated_save()

    def _setup_locations(self):
        for _location_type in GLOBAL_YAML_SETTINGS["location_type"]:
            _parent = None
            _content_types = []
            if _location_type["parent"]:
                _parent = LocationType.objects.get(name=_location_type["parent"])
            try:
                location_type = LocationType.objects.get(name=_location_type["name"], parent=_parent)
            except LocationType.DoesNotExist:
                location_type = LocationType.objects.create(
                    name=_location_type["name"],
                    parent=_parent,
                    nestable=_location_type["nestable"] if _location_type["nestable"] != "" else False,
                    description=_location_type["description"],
                )
            location_type.validated_save()
            location_type.custom_field_data["system_of_record"] = "Bootstrap"
            for _con_type in _location_type["content_types"]:
                _content_types.append(
                    ContentType.objects.get(app_label=_con_type.split(".")[0], model=_con_type.split(".")[1])
                )
            location_type.content_types.set(_content_types)
            location_type.validated_save()

        for _location in GLOBAL_YAML_SETTINGS["location"]:
            _parent = None
            _tenant = None
            _timezone = None
            _tags = []
            _location_type = LocationType.objects.get(name=_location["location_type"])
            _status = Status.objects.get(name=_location["status"])
            if "parent" in _location:
                if _location["parent"]:
                    _parent = Location.objects.get(name=_location["parent"])
            if "tenant" in _location:
                if _location["tenant"]:
                    _tenant = Tenant.objects.get(name=_location["tenant"])
            if "time_zone" in _location:
                if _location["time_zone"]:
                    if is_valid_timezone(_location["time_zone"]):
                        _timezone = _location["time_zone"]
            if "tags" in _location:
                for _tag in _location["tags"]:
                    _tags.append(Tag.get(name=_tag))
            location, _ = Location.objects.get_or_create(
                name=_location["name"],
                location_type=_location_type,
                parent=_parent if not None else None,
                status=_status,
            )
            if _location["facility"]:
                location.facility = _location["facility"]
            if _location["asn"]:
                location.asn = _location["asn"]
            if _timezone is not None:
                location.time_zone = _timezone
            if _location["description"]:
                location.description = _location["description"]
            if _tenant is not None:
                location.tenant = (_tenant,)
            if _location["physical_address"]:
                location.physical_address = _location["physical_address"]
            if _location["shipping_address"]:
                location.shipping_address = _location["shipping_address"]
            if _location["latitude"]:
                location.latitude = _location["latitude"]
            if _location["longitude"]:
                location.longitude = _location["longitude"]
            if _location["contact_name"]:
                location.contact_name = _location["contact_name"]
            if _location["contact_phone"]:
                location.contact_phone = _location["contact_phone"]
            if _location["contact_email"]:
                location.contact_email = _location["contact_email"]
            location.validated_save()
            location.custom_field_data["system_of_record"] = "Bootstrap"
            for _tag in _tags:
                location.tags.add(_tag)
            location.validated_save()

    def _setup_tenant_groups(self):
        _tenant_groups = [
            {
                "name": "Group1",
                "parent": "",
            },
            {
                "name": "Group2",
                "parent": "",
            },
            {
                "name": "Group3",
                "parent": "Group1",
            },
        ]
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
        _tenants = ["Backbone", "Datacenter"]
        for _ten in _tenants:
            _tenant = Tenant.objects.create(name=_ten)
            _tenant.custom_field_data["system_of_record"] = "Bootstrap"
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
                name=_role["name"], color=_role["color"], description=_role["description"]
            )
            if created:
                _r.content_types.set(_con_types)
                _r.custom_field_data["system_of_record"] = "Bootstrap"
                _r.validated_save()
            _con_types.clear()

    def _setup_teams(self):
        for _team in GLOBAL_YAML_SETTINGS["team"]:
            team = Team.objects.create(
                name=_team["name"], phone=_team["phone"], email=_team["email"], address=_team["address"]
            )
            team.custom_field_data["system_of_record"] = "Bootstrap"
            team.validated_save()

    def _setup_contacts(self):
        for _contact in GLOBAL_YAML_SETTINGS["contact"]:
            contact = Contact.objects.create(
                name=_contact["name"], phone=_contact["phone"], email=_contact["email"], address=_contact["address"]
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
            rir.private = _rir["private"]
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

    def _setup_prefixes(self):
        for _prefix in GLOBAL_YAML_SETTINGS["prefix"]:
            _namespace = Namespace.objects.get(name="Global")
            _prefix_type = "network"
            _role = None
            _rir = None
            _vrfs = []
            _locations = []
            _vlan = None
            _tenant = None
            _tags = []
            if _prefix["namespace"] and _prefix["namespace"] != "Global":
                _namespace = Namespace.objects.get(name=_prefix["namespace"])
            if _prefix["prefix_type"] and _prefix["prefix_type"] != "network":
                _prefix_type = _prefix["prefix_type"]
            if _prefix["role"]:
                _role = Role.objects.get(name=_prefix["role"])
            if _prefix["rir"]:
                _rir = RIR.objects.get(name=_prefix["rir"])
            if _prefix["vrfs"]:
                for _v in _prefix["vrfs"]:
                    _namespace = Namespace.objects.get(name=_v.split("__")[1])
                    _vrfs.append(VRF.objects.get(name=_v.split("__")[0], namespace=_namespace))
            if _prefix["locations"]:
                for _l in _prefix["locations"]:
                    _locations.append(Location.objects.get(name=_l))
            if _prefix["vlan"]:
                _name, _vid, _group = _prefix["vlan"].split("__", 2)
                if _group is not None:
                    _vlan_group = VLANGroup.objects.get(name=_group)
                _vlan = VLAN.objects.get(name=_name, vid=_vid, vlan_group=_vlan_group)
            if _prefix["tenant"]:
                _tenant = Tenant.objects.get(name=_prefix["tenant"])
            if _prefix["tags"]:
                for _t in _prefix["tags"]:
                    _tags.append(Tag.objects.get(name=_t))
            try:
                prefix = Prefix.objects.get(
                    network=_prefix["network"].split("/")[0],
                    prefix_length=_prefix["network"].split("/")[1],
                    namespace=_namespace,
                    type=_prefix_type,
                )
            except Prefix.DoesNotExist:
                prefix = Prefix.objects.create(
                    network=_prefix["network"].split("/")[0],
                    prefix_length=_prefix["network"].split("/")[1],
                    namespace=_namespace,
                    type=_prefix_type,
                    status=Status.objects.get(name=_prefix["status"]),
                    role=_role,
                    rir=_rir,
                    date_allocated=_prefix["date_allocated"],
                    description=_prefix["description"],
                    vlan=_vlan,
                    tenant=_tenant,
                )
            prefix.custom_field_data["system_of_record"] = "Bootstrap"
            prefix.validated_save()
            for _l in _locations:
                prefix.locations.add(_l)
            for _v in _vrfs:
                prefix.vrfs.add(_v)

    def _setup_manufacturers_and_platforms(self):
        _manufacturers = ["Arista", "Palo Alto Networks", "Cisco", "Generic"]
        _platforms = [
            {"manufacturer": "Arista", "platform": "arista_eos"},
            {"manufacturer": "Palo Alto Networks", "platform": "paloalto_panos"},
            {"manufacturer": "Cisco", "platform": "cisco_ios"},
        ]
        for _manufacturer in _manufacturers:
            _manufac = Manufacturer.objects.create(name=_manufacturer)
            _manufac.custom_field_data["system_of_record"] = "Bootstrap"
            _manufac.validated_save()
        for _platform in _platforms:
            _manufac = Manufacturer.objects.get(name=_platform["manufacturer"])
            _platf = Platform.objects.create(name=_platform["platform"], manufacturer=_manufac)
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
            _secrets_group.save()
            _secrets_group.refresh_from_db()
            for _sec in _sec_group["secrets"]:
                _sga = SecretsGroupAssociation.objects.create(
                    secrets_group=_secrets_group,
                    secret=Secret.objects.get(name=_sec["name"]),
                    access_type=_sec["access_type"],
                    secret_type=_sec["secret_type"],
                )
                _sga.save()
                _sga.refresh_from_db()

    def _setup_computed_fields(self):
        for _comp_field in GLOBAL_YAML_SETTINGS["computed_field"]:
            _content_type = ContentType.objects.get(
                app_label=_comp_field["content_type"].split(".")[0], model=_comp_field["content_type"].split(".")[1]
            )
            _computed_field = ComputedField.objects.create(
                label=_comp_field["label"], content_type=_content_type, template=_comp_field["template"]
            )
            _computed_field.save()
            _computed_field.refresh_from_db()

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
            if _repo.get("secrets_group"):
                _secrets_group = SecretsGroup.objects.get(name=_repo["secrets_group"])
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
                app_label=_group["content_type"].split(".")[0], model=_group["content_type"].split(".")[1]
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
        for _software in GLOBAL_YAML_SETTINGS["software"]:
            _tags = []
            for _tag in _software["tags"]:
                _tags.append(Tag.objects.get(name=_tag))
            _platform = Platform.objects.get(name=_software["device_platform"])
            _soft = SoftwareLCM.objects.create(
                version=_software["version"],
                alias=_software["alias"],
                device_platform=_platform,
                end_of_support=_software["eos_date"],
                long_term_support=_software["lts"],
                pre_release=_software["pre_release"],
                documentation_url=_software["documentation_url"],
                tags=_tags,
            )
            _soft.custom_field_data["system_of_record"] = "Bootstrap"
            _soft.validated_save()
            _soft.refresh_from_db()

        for _software_image in GLOBAL_YAML_SETTINGS["software_image"]:
            _tags = []
            for _tag in _software_image["tags"]:
                _tags.append(Tag.objects.get(name=_tag))
            _platform = Platform.objects.get(name=_software_image["platform"])
            _software = SoftwareLCM.objects.get(version=_software_image["software_version"], device_platform=_platform)
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
        for _validated_software in GLOBAL_YAML_SETTINGS["validated_software"]:
            _tags = []
            _devices = []
            _device_types = []
            _device_roles = []
            _inventory_items = []
            _object_tags = []
            for _tag in _validated_software["tags"]:
                _tags.append(Tag.objects.get(name=_tag))
            for _dev in _validated_software["devices"]:
                _devices.append(Device.objects.get(name=_dev))
            for _dev_type in _validated_software["device_types"]:
                _device_types.append(DeviceType.objects.get(model=_dev_type))
            for _dev_role in _validated_software["device_roles"]:
                _device_roles.append(Role.objects.get(name=_dev_role))
            for _inv_item in _validated_software["inventory_items"]:
                _inventory_items.append(InventoryItem.objects.get(name=_inv_item))
            for _obj_tag in _validated_software["object_tags"]:
                _object_tags.append(Tag.objects.get(name=_obj_tag))
            _platform = Platform.objects.get(name=_validated_software["software"].split(" - ")[0])
            _software = SoftwareLCM.objects.get(
                version=_validated_software["software"].split(" - ")[1], device_platform=_platform
            )
            _valid_software = ValidatedSoftwareLCM.objects.create(
                software=_software,
                start=_validated_software["valid_since"],
                end=_validated_software["valid_until"],
                preferred=_validated_software["preferred_version"],
                tags=_tags,
            )
            _valid_software.custom_field_data["system_of_record"] = "Bootstrap"
            _valid_software.validated_save()
            _valid_software.devices.set(_devices)
            _valid_software.device_types.set(_device_types)
            _valid_software.device_roles.set(_device_roles)
            _valid_software.inventory_items.set(_inventory_items)
            _valid_software.object_tags.set(_object_tags)
            _valid_software.validated_save()
