"""Nautobot Ssot Bootstrap Adapter for bootstrap SSoT plugin."""

import datetime
import json
import os

import yaml
from diffsync import Adapter
from diffsync.exceptions import ObjectAlreadyExists, ObjectNotFound
from django.conf import settings
from nautobot.extras.datasources.git import ensure_git_repository
from nautobot.extras.models import GitRepository

from nautobot_ssot.integrations.bootstrap.diffsync.models.bootstrap import (
    BootstrapCircuit,
    BootstrapCircuitTermination,
    BootstrapCircuitType,
    BootstrapComputedField,
    BootstrapContact,
    BootstrapDynamicGroup,
    BootstrapGitRepository,
    BootstrapGraphQLQuery,
    BootstrapLocation,
    BootstrapLocationType,
    BootstrapManufacturer,
    BootstrapNamespace,
    BootstrapPlatform,
    BootstrapPrefix,
    BootstrapProvider,
    BootstrapProviderNetwork,
    BootstrapRiR,
    BootstrapRole,
    BootstrapSecret,
    BootstrapSecretsGroup,
    BootstrapTag,
    BootstrapTeam,
    BootstrapTenant,
    BootstrapTenantGroup,
    BootstrapVLAN,
    BootstrapVLANGroup,
    BootstrapVRF,
)
from nautobot_ssot.integrations.bootstrap.utils import (
    is_running_tests,
    lookup_content_type,
)

try:
    import nautobot_device_lifecycle_mgmt  # noqa: F401

    LIFECYCLE_MGMT = True
except ImportError:
    LIFECYCLE_MGMT = False

if LIFECYCLE_MGMT:
    from nautobot_ssot.integrations.bootstrap.diffsync.models.bootstrap import (  # noqa: F401
        BootstrapSoftware,
        BootstrapSoftwareImage,
        BootstrapValidatedSoftware,
    )


class LabelMixin:
    """Add labels onto Nautobot objects to provide information on sync status with Bootstrap."""

    def label_imported_objects(self, target):
        """Add CustomFields to all objects that were successfully synced to the target."""
        _model_list = [
            "tag",
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
            "namespace",
            "rir",
            "vlan_group",
            "vlan",
            "vrf",
            "prefix",
            "secret",
            "secrets_group",
            "git_repository",
            "dynamic_group",
            "computed_field",
            "graph_ql_query",
        ]

        if LIFECYCLE_MGMT:
            _model_list.append(
                "software",
                "software_image",
                "validated_software",
            )

        for modelname in _model_list:
            for local_instance in self.get_all(modelname):
                unique_id = local_instance.get_unique_id()
                # Verify that the object now has a counterpart in the target DiffSync
                try:
                    target.get(modelname, unique_id)
                except ObjectNotFound:
                    continue

                self.label_object(modelname, unique_id)

    def label_object(self, modelname, unique_id):
        """Apply the given CustomField to the identified object."""

        def _label_object(nautobot_object):
            """Apply custom field to object, if applicable."""
            nautobot_object.custom_field_data["last_synced_from_sor"] = today
            nautobot_object.custom_field_data["system_of_record"] = os.getenv("SYSTEM_OF_RECORD", "Bootstrap")
            nautobot_object.validated_save()

        today = datetime.today().date().isoformat()


class BootstrapAdapter(Adapter, LabelMixin):
    """DiffSync adapter for Bootstrap."""

    tenant_group = BootstrapTenantGroup
    tenant = BootstrapTenant
    role = BootstrapRole
    manufacturer = BootstrapManufacturer
    platform = BootstrapPlatform
    location_type = BootstrapLocationType
    location = BootstrapLocation
    team = BootstrapTeam
    contact = BootstrapContact
    provider = BootstrapProvider
    provider_network = BootstrapProviderNetwork
    circuit_type = BootstrapCircuitType
    circuit = BootstrapCircuit
    circuit_termination = BootstrapCircuitTermination
    namespace = BootstrapNamespace
    rir = BootstrapRiR
    vlan_group = BootstrapVLANGroup
    vlan = BootstrapVLAN
    vrf = BootstrapVRF
    prefix = BootstrapPrefix
    secret = BootstrapSecret
    secrets_group = BootstrapSecretsGroup
    git_repository = BootstrapGitRepository
    dynamic_group = BootstrapDynamicGroup
    computed_field = BootstrapComputedField
    tag = BootstrapTag
    graph_ql_query = BootstrapGraphQLQuery

    if LIFECYCLE_MGMT:
        software = BootstrapSoftware
        software_image = BootstrapSoftwareImage
        validated_software = BootstrapValidatedSoftware

    top_level = [
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
        "namespace",
        "rir",
        "vlan_group",
        "vlan",
        "vrf",
        "prefix",
        "secret",
        "secrets_group",
        "git_repository",
        "dynamic_group",
        "computed_field",
        "tag",
        "graph_ql_query",
    ]

    if LIFECYCLE_MGMT:
        top_level.append("software")
        top_level.append("software_image")
        top_level.append("validated_software")

    def __init__(self, *args, job=None, sync=None, client=None, **kwargs):  # noqa: D417
        """Initialize bootstrap.

        Args:
            job (object, optional): bootstrap job. Defaults to None.
            sync (object, optional): bootstrap DiffSync. Defaults to None.
            client (object): bootstrap API client connection object.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.conn = client

    def load_tenant_group(self, bs_tenant_group, branch_vars):
        """Load TenantGroup objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap TenantGroup: {bs_tenant_group}")

        try:
            self.get(self.tenant_group, bs_tenant_group["name"])
        except ObjectNotFound:
            new_tenant_group = self.tenant_group(
                name=bs_tenant_group["name"],
                parent=bs_tenant_group["parent"] if not None else None,
                description=bs_tenant_group["description"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_tenant_group)

    def load_tenant(self, bs_tenant, branch_vars):
        """Load Tenant objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap Tenant: {bs_tenant}")

        try:
            self.get(self.tenant, bs_tenant["name"])
        except ObjectNotFound:
            new_tenant = self.tenant(
                name=bs_tenant["name"],
                tenant_group=bs_tenant["tenant_group"] if not None else None,
                description=bs_tenant["description"],
                tags=bs_tenant["tags"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_tenant)

    def load_role(self, bs_role, branch_vars):
        """Load Role objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap Role {bs_role}")

        if len(bs_role["content_types"]) > 1:
            _content_types = bs_role["content_types"]
            _content_types.sort()
        else:
            _content_types = bs_role["content_types"]
        try:
            self.get(self.role, bs_role["name"])
        except ObjectNotFound:
            new_role = self.role(
                name=bs_role["name"],
                weight=bs_role["weight"],
                description=bs_role["description"],
                color=bs_role["color"] if not None else "9e9e9e",
                content_types=_content_types,
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_role)

    def load_manufacturer(self, bs_manufacturer, branch_vars):
        """Load Manufacturer objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Boostrap Manufacturer {bs_manufacturer}")

        try:
            self.get(self.manufacturer, bs_manufacturer["name"])
        except ObjectNotFound:
            new_manufacturer = self.manufacturer(
                name=bs_manufacturer["name"],
                description=bs_manufacturer["description"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_manufacturer)

    def load_platform(self, bs_platform, branch_vars):
        """Load Platform objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap Platform {bs_platform}")

        try:
            self.get(self.platform, bs_platform["name"])
        except ObjectNotFound:
            new_platform = self.platform(
                name=bs_platform["name"],
                manufacturer=bs_platform["manufacturer"],
                network_driver=bs_platform["network_driver"],
                napalm_driver=bs_platform["napalm_driver"],
                napalm_arguments=bs_platform["napalm_arguments"],
                description=bs_platform["description"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_platform)

    def load_location_type(self, bs_location_type, branch_vars):
        """Load LocationType objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap LocationType {bs_location_type}")

        try:
            self.get(self.location_type, bs_location_type["name"])
        except ObjectNotFound:
            _content_types = []
            if bs_location_type["parent"]:
                _parent = bs_location_type["parent"]
            else:
                _parent = None
            if len(bs_location_type["content_types"]) > 1:
                _content_types = bs_location_type["content_types"]
                _content_types.sort()
            new_location_type = self.location_type(
                name=bs_location_type["name"],
                parent=_parent,
                nestable=bs_location_type["nestable"],
                description=bs_location_type["description"],
                content_types=_content_types,
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_location_type)

    def load_location(self, bs_location, branch_vars):
        """Load Location objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap Location {bs_location}")

        try:
            self.get(self.location, bs_location["name"])
        except ObjectNotFound:
            if bs_location["parent"]:
                _parent = bs_location["parent"]
            else:
                _parent = None
            if bs_location["tenant"]:
                _tenant = bs_location["tenant"]
            else:
                _tenant = None
            new_location = self.location(
                name=bs_location["name"],
                location_type=bs_location["location_type"],
                parent=_parent,
                status=bs_location["status"],
                facility=bs_location["facility"],
                asn=bs_location["asn"],
                time_zone=bs_location["time_zone"],
                description=bs_location["description"],
                tenant=_tenant,
                physical_address=bs_location["physical_address"],
                shipping_address=bs_location["shipping_address"],
                latitude=bs_location["latitude"],
                longitude=bs_location["longitude"],
                contact_name=bs_location["contact_name"],
                contact_phone=bs_location["contact_phone"],
                contact_email=bs_location["contact_email"],
                tags=bs_location["tags"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_location)

    def load_team(self, bs_team, branch_vars):
        """Load Team objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap Team {bs_team}")

        if "contacts" in bs_team:
            _contacts = []
            for _contact in bs_team["contacts"]:
                _contacts.append(_contact)
                _contacts.sort()
        try:
            self.get(self.team, bs_team["name"])
        except ObjectNotFound:
            new_team = self.team(
                name=bs_team["name"],
                phone=bs_team["phone"],
                email=bs_team["email"],
                address=bs_team["address"],
                # TODO: Need to consider how to allow loading from teams or contacts models.
                # contacts=_contacts,
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_team)

    def load_contact(self, bs_contact, branch_vars):
        """Load Contact objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Boostrap Contact {bs_contact}")

        if "teams" in bs_contact:
            _teams = []
            for _team in bs_contact["teams"]:
                _teams.append(_team)
                _teams.sort()
        try:
            self.get(self.contact, bs_contact["name"])
        except ObjectNotFound:
            new_contact = self.contact(
                name=bs_contact["name"],
                phone=bs_contact["phone"],
                email=bs_contact["email"],
                address=bs_contact["address"],
                teams=_teams,
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_contact)

    def load_provider(self, bs_provider, branch_vars):
        """Load Provider objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap Provider {bs_provider}")

        try:
            self.get(self.provider, bs_provider["name"])
        except ObjectNotFound:
            new_provider = self.provider(
                name=bs_provider["name"],
                asn=bs_provider["asn"],
                account_number=bs_provider["account_number"],
                portal_url=bs_provider["portal_url"],
                noc_contact=bs_provider["noc_contact"],
                admin_contact=bs_provider["admin_contact"],
                tags=bs_provider["tags"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_provider)

    def load_provider_network(self, bs_provider_network, branch_vars):
        """Load ProviderNetwork objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap ProviderNetwork {bs_provider_network}")

        try:
            self.get(self.provider_network, bs_provider_network["name"])
        except ObjectNotFound:
            new_provider_network = self.provider_network(
                name=bs_provider_network["name"],
                provider=bs_provider_network["provider"],
                description=bs_provider_network["description"],
                comments=bs_provider_network["comments"],
                tags=bs_provider_network["tags"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_provider_network)

    def load_circuit_type(self, bs_circuit_type, branch_vars):
        """Load CircuitType objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap CircuitType {bs_circuit_type} into DiffSync models.")

        try:
            self.get(self.circuit_type, bs_circuit_type["name"])
        except ObjectNotFound:
            new_circuit_type = self.circuit_type(
                name=bs_circuit_type["name"],
                description=bs_circuit_type["description"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_circuit_type)

    def load_circuit(self, bs_circuit, branch_vars):
        """Load Circuit objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap Circuit {bs_circuit} into DiffSync models.")

        try:
            self.get(self.circuit, bs_circuit["circuit_id"])
        except ObjectNotFound:
            new_circuit = self.circuit(
                circuit_id=bs_circuit["circuit_id"],
                provider=bs_circuit["provider"],
                circuit_type=bs_circuit["circuit_type"],
                status=bs_circuit["status"],
                date_installed=bs_circuit["date_installed"],
                commit_rate_kbps=bs_circuit["commit_rate_kbps"],
                description=bs_circuit["description"],
                tags=bs_circuit["tags"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_circuit)

    def load_circuit_termination(self, bs_circuit_termination, branch_vars):
        """Load CircuitTermination objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(
                f"Loading Bootstrap CircuitTermination {bs_circuit_termination} into DiffSync models."
            )
        _parts = bs_circuit_termination["name"].split("__")
        _circuit_id = _parts[0]
        _provider = _parts[1]
        _term_side = _parts[2]
        try:
            self.get(self.circuit_termination, bs_circuit_termination["name"])
        except ObjectNotFound:
            new_circuit_termination = self.circuit_termination(
                name=bs_circuit_termination["name"],
                termination_type=bs_circuit_termination["termination_type"],
                termination_side=_term_side,
                circuit_id=_circuit_id,
                location=(bs_circuit_termination["location"] if bs_circuit_termination["location"] != "" else None),
                provider_network=(
                    bs_circuit_termination["provider_network"]
                    if bs_circuit_termination["provider_network"] != ""
                    else None
                ),
                port_speed_kbps=bs_circuit_termination["port_speed_kbps"],
                upstream_speed_kbps=bs_circuit_termination["upstream_speed_kbps"],
                cross_connect_id=bs_circuit_termination["cross_connect_id"],
                patch_panel_or_ports=bs_circuit_termination["patch_panel_or_ports"],
                description=bs_circuit_termination["description"],
                tags=bs_circuit_termination["tags"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_circuit_termination)
            try:
                _circuit = self.get(self.circuit, {"circuit_id": _circuit_id, "provider": _provider})
                _circuit.add_child(new_circuit_termination)
            except ObjectAlreadyExists as err:
                self.job.logger.warning(f"CircuitTermination for {_circuit} already exists. {err}")
            except ObjectNotFound as err:
                self.job.logger.warning(f"Circuit {_circuit_id} not found. {err}")

    def load_namespace(self, bs_namespace, branch_vars):
        """Load Namespace objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap Namespace {bs_namespace}.")
        try:
            self.get(self.namespace, bs_namespace["name"])
        except ObjectNotFound:
            new_namespace = self.namespace(
                name=bs_namespace["name"],
                description=bs_namespace["description"],
                location=bs_namespace["location"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_namespace)

    def load_rir(self, bs_rir, branch_vars):
        """Load RiR objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap RiR {bs_rir}.")
        try:
            self.get(self.rir, bs_rir["name"])
        except ObjectNotFound:
            new_rir = self.rir(
                name=bs_rir["name"],
                private=bs_rir["private"] if bs_rir["private"] else False,
                description=bs_rir["description"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_rir)

    def load_vlan_group(self, bs_vlan_group, branch_vars):
        """Load VLANGroup objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap VLANGroup {bs_vlan_group}.")
        try:
            self.get(self.vlan_group, bs_vlan_group["name"])
        except ObjectNotFound:
            new_vlan_group = self.vlan_group(
                name=bs_vlan_group["name"],
                location=bs_vlan_group["location"],
                description=bs_vlan_group["description"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_vlan_group)

    def load_vlan(self, bs_vlan, branch_vars):
        """Load VLAN objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap VLAN {bs_vlan}.")
        try:
            self.get(
                self.vlan,
                {
                    "name": bs_vlan["name"],
                    "vid": bs_vlan["vid"],
                    "vlan_group": (bs_vlan["vlan_group"] if bs_vlan["vlan_group"] else None),
                },
            )
        except ObjectNotFound:
            new_vlan = self.vlan(
                name=bs_vlan["name"],
                vid=bs_vlan["vid"],
                description=bs_vlan["description"],
                status=bs_vlan["status"] if bs_vlan["status"] else "Active",
                role=bs_vlan["role"] if bs_vlan["role"] else None,
                locations=bs_vlan["locations"],
                vlan_group=bs_vlan["vlan_group"] if bs_vlan["vlan_group"] else None,
                tenant=bs_vlan["tenant"] if bs_vlan["tenant"] else None,
                tags=bs_vlan["tags"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_vlan)

    def load_vrf(self, bs_vrf, branch_vars):
        """Load VRF objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap VRF {bs_vrf}.")
        try:
            self.get(
                self.vrf,
                {
                    "name": bs_vrf["name"],
                    "namespace": (bs_vrf["namespace"] if bs_vrf["namespace"] else "Global"),
                },
            )
        except ObjectNotFound:
            new_vrf = self.vrf(
                name=bs_vrf["name"],
                namespace=bs_vrf["namespace"] if bs_vrf["namespace"] else "Global",
                route_distinguisher=bs_vrf["route_distinguisher"],
                description=bs_vrf["description"],
                tenant=bs_vrf["tenant"] if bs_vrf["tenant"] else None,
                tags=bs_vrf["tags"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_vrf)

    def load_prefix(self, bs_prefix, branch_vars):
        """Load Prefix objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap Prefix {bs_prefix}.")
        try:
            self.get(
                self.prefix,
                {
                    "network": {bs_prefix["network"]},
                    "namespace": {bs_prefix["namespace"] if bs_prefix["namespace"] else "Global"},
                },
            )
        except ObjectNotFound:
            _date_allocated = None
            if "date_allocated" in bs_prefix and bs_prefix["date_allocated"]:
                if isinstance(bs_prefix["date_allocated"], (datetime.date, datetime.datetime)):
                    _date_allocated = bs_prefix["date_allocated"]
                    if isinstance(_date_allocated, datetime.date) and not isinstance(
                        _date_allocated, datetime.datetime
                    ):
                        _date_allocated = datetime.datetime.combine(_date_allocated, datetime.time.min)
                else:
                    try:
                        _date_allocated = datetime.datetime.strptime(bs_prefix["date_allocated"], "%Y-%m-%d %H:%M:%S")
                    except (TypeError, ValueError):
                        try:
                            _date_allocated = datetime.datetime.strptime(bs_prefix["date_allocated"], "%Y-%m-%d")
                            _date_allocated = _date_allocated.replace(hour=0, minute=0, second=0)
                        except (TypeError, ValueError):
                            _date_allocated = None
                            self.job.logger.warning(
                                f"Invalid date format for date_allocated: {bs_prefix['date_allocated']}"
                            )
            new_prefix = self.prefix(
                network=bs_prefix["network"],
                namespace=(bs_prefix["namespace"] if bs_prefix["namespace"] else "Global"),
                prefix_type=(bs_prefix["prefix_type"] if bs_prefix["prefix_type"] else "Network"),
                status=bs_prefix["status"] if bs_prefix["status"] else "Active",
                role=bs_prefix["role"] if bs_prefix["role"] else None,
                rir=bs_prefix["rir"] if bs_prefix["rir"] else None,
                date_allocated=_date_allocated,
                description=bs_prefix["description"],
                vrfs=bs_prefix["vrfs"] if bs_prefix["vrfs"] else None,
                locations=bs_prefix["locations"] if bs_prefix["locations"] else None,
                vlan=bs_prefix["vlan"] if bs_prefix["vlan"] else None,
                tenant=bs_prefix["tenant"] if bs_prefix["tenant"] else None,
                tags=bs_prefix["tags"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_prefix)

    def load_secret(self, bs_secret, branch_vars):
        """Load Secret objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap Secret: {bs_secret}")
        if bs_secret["provider"] == "environment-variable":
            params = {"variable": bs_secret["parameters"]["variable"]}
        elif bs_secret["provider"] == "text-file":
            params = {"variable": bs_secret["parameters"]["path"]}
        else:
            self.job.logger.warning(f"Secret: {bs_secret} is not formatted correctly in the yaml file.")
            return

        try:
            self.get(self.secret, bs_secret["name"])
        except ObjectNotFound:
            new_secret = self.secret(
                name=bs_secret["name"],
                provider=bs_secret["provider"],
                parameters=params,
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_secret)

    def load_secrets_group(self, bs_sg, branch_vars):
        """Load SecretsGroup objects from Bootstrap into DiffSync models."""
        _secrets = []
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap SecretsGroup: {bs_sg}")
        try:
            self.get(self.secrets_group, bs_sg["name"])
        except ObjectNotFound:
            for _sec in bs_sg["secrets"]:
                _secrets.append(_sec)
            _secrets = sorted(_secrets, key=lambda x: x["name"])
            new_secrets_group = self.secrets_group(
                name=bs_sg["name"],
                secrets=_secrets,
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_secrets_group)

    def load_git_repository(self, git_repo, branch_vars):
        """Load GitRepository objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap GitRepository: {git_repo}")
        try:
            self.get(self.git_repository, git_repo["name"])
        except ObjectNotFound:
            _data_types = []
            for con_type in git_repo["provided_data_type"]:
                _content_type = lookup_content_type(content_model_path="extras.gitrepository", content_type=con_type)
                _data_types.append(_content_type)
            if git_repo.get("branch"):
                _branch = git_repo["branch"]
            else:
                _branch = branch_vars["git_branch"]
            new_git_repository = self.git_repository(
                name=git_repo["name"],
                url=git_repo["url"],
                branch=_branch,
                provided_contents=_data_types,
                secrets_group=git_repo["secrets_group_name"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_git_repository)
            _data_types.clear()

    def load_dynamic_group(self, dyn_group):
        """Load DynamicGroup objects from Bootstrap into DiffSync models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap DynamicGroup: {dyn_group}")
        try:
            self.get(self.dynamic_group, dyn_group["name"])
        except ObjectNotFound:
            new_dynamic_group = self.dynamic_group(
                name=dyn_group["name"],
                content_type=dyn_group["content_type"],
                dynamic_filter=json.loads(dyn_group["filter"]),
                description=dyn_group["description"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(new_dynamic_group)

    def load_computed_field(self, comp_field):
        """Load ComputedField objects from Bootstrap into DiffSync Models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap ComputedField: {comp_field}")
        try:
            self.get(self.computed_field, comp_field["label"])
        except ObjectNotFound:
            _new_comp_field = self.computed_field(
                label=comp_field["label"],
                content_type=comp_field["content_type"],
                template=comp_field["template"],
            )
            self.add(_new_comp_field)

    def load_tag(self, tag):
        """Load Tag objects from Bootstrap into DiffSync Models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap Tag: {tag}")
        if len(tag["content_types"]) > 1:
            _content_types = tag["content_types"]
            _content_types.sort()
        else:
            _content_types = tag["content_types"]
        try:
            self.get(self.tag, tag["name"])
        except ObjectNotFound:
            _new_tag = self.tag(
                name=tag["name"],
                color=tag["color"] if not None else "9e9e9e",
                content_types=_content_types,
                description=tag["description"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(_new_tag)

    def load_graph_ql_query(self, query):
        """Load GraphQLQuery objects from Bootstrap into DiffSync Models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap GraphQLQuery {query}")
        try:
            self.get(self.graph_ql_query, query["name"])
        except ObjectNotFound:
            _new_graphqlq = self.graph_ql_query(name=query["name"], query=query["query"])
            self.add(_new_graphqlq)

    def load_software(self, software):
        """Load Software objects from Bootstrap into DiffSync Models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap Software {software}")
        try:
            self.get(
                self.software,
                {
                    "version": software["version"],
                    "platform": software["device_platform"],
                },
            )
        except ObjectNotFound:
            try:
                _release_date = datetime.datetime.strptime(software["release_date"], "%Y-%m-%d")
            except TypeError:
                _release_date = None
            try:
                _eos_date = datetime.datetime.strptime(software["eos_date"], "%Y-%m-%d")
            except TypeError:
                _eos_date = None
            if software["documentation_url"] is None:
                _documentation_url = ""
            else:
                _documentation_url = software["documentation_url"]
            _new_software = self.software(
                version=software["version"],
                platform=software["device_platform"],
                alias=software["alias"] if not None else "",
                release_date=_release_date,
                eos_date=_eos_date,
                documentation_url=_documentation_url,
                long_term_support=software["lts"],
                pre_release=software["pre_release"],
                tags=software["tags"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(_new_software)

    def load_software_image(self, software_image):
        """Load SoftwareImage objects from Bootstrap into DiffSync Models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap SoftwareImage {software_image}")
        try:
            self.get(self.software_image, software_image["file_name"])
        except ObjectNotFound:
            _new_software_image = self.software_image(
                software=f'{software_image["platform"]} - {software_image["software_version"]}',
                platform=software_image["platform"],
                software_version=software_image["software_version"],
                file_name=software_image["file_name"],
                download_url=software_image["download_url"],
                image_file_checksum=software_image["image_file_checksum"],
                hashing_algorithm=software_image["hashing_algorithm"],
                default_image=software_image["default_image"] if not None else False,
                tags=software_image["tags"],
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(_new_software_image)

    def load_validated_software(self, validated_software):
        """Load ValidatedSoftware objects from Bootstrap into DiffSync Models."""
        if self.job.debug:
            self.job.logger.debug(f"Loading Bootstrap ValidatedSoftware {validated_software}")
        try:
            self.get(
                self.validated_software,
                {
                    "software": {validated_software["software"]},
                    "valid_since": {validated_software["valid_since"]},
                    "valid_until": {validated_software["valid_until"]},
                },
            )
        except ObjectNotFound:
            _new_validated_software = self.validated_software(
                software=validated_software["software"],
                software_version=validated_software["software"].split(" - ", 1)[1],
                platform=validated_software["software"].split(" - ", 1)[0],
                valid_since=validated_software["valid_since"],
                valid_until=validated_software["valid_until"],
                preferred_version=validated_software["preferred_version"],
                devices=sorted(validated_software["devices"]),
                device_types=sorted(validated_software["device_types"]),
                device_roles=sorted(validated_software["device_roles"]),
                inventory_items=sorted(validated_software["inventory_items"]),
                object_tags=sorted(validated_software["object_tags"]),
                tags=sorted(validated_software["tags"]),
                system_of_record=os.getenv("SYSTEM_OF_RECORD", "Bootstrap"),
            )
            self.add(_new_validated_software)

    def load(self):
        """Load data from Bootstrap into DiffSync models."""
        environment_label = settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_nautobot_environment_branch"]

        if is_running_tests():
            load_type = "file"
        elif self.job.load_source == "env_var":
            load_type = os.getenv("NAUTOBOT_BOOTSTRAP_SSOT_LOAD_SOURCE", "file")
        else:
            load_type = self.job.load_source

        global global_settings
        global_settings = None

        if load_type == "file":
            directory_path = "nautobot_ssot/integrations/bootstrap/fixtures"
            # generates a variable for each file in fixtures named the same as the file name less .yaml
            for filename in os.listdir(directory_path):
                if filename.endswith(".yaml") or filename.endswith(".yml"):
                    with open(os.path.join(directory_path, filename), "r") as file:
                        yaml_data = yaml.safe_load(file)
                    variable_name = os.path.splitext(filename)[0]
                    globals()[variable_name] = yaml_data

            branch_vars = globals()[environment_label]
            global_settings = globals().get("global_settings")

        elif load_type == "git":
            repo = GitRepository.objects.filter(
                name__icontains="Bootstrap",
                provided_contents__icontains="extras.configcontext",
            )
            if len(repo) == 0:
                self.job.logger.warning(
                    "Unable to find Bootstrap SSoT Repository configured in Nautobot, please ensure a git repository with a name containing 'Bootstrap' is present and provides 'configcontext' type."
                )
            else:
                repo = repo[0]
                if self.job.debug:
                    self.job.logger.debug(f"Sync the {repo.name} GitRepository.")
                ensure_git_repository(repository_record=repo)
                self.job.logger.info(f"Parsing the {repo.name} GitRepository.")
                os.chdir(f"{repo.filesystem_path}")
                directory_path = "./"
                # generates a variable for each file in fixtures named the same as the file name less .yaml
                for filename in os.listdir("./"):
                    if filename.endswith(".yaml") or filename.endswith(".yml"):
                        with open(os.path.join(directory_path, filename), "r") as file:
                            yaml_data = yaml.safe_load(file)
                        variable_name = os.path.splitext(filename)[0]
                        globals()[variable_name] = yaml_data

                branch_vars = globals()[environment_label]
                global_settings = globals().get("global_settings")

        # Ensure global_settings is loaded
        if global_settings is None:
            self.job.logger.error("global_settings not loaded. Check if the file exists in the correct directory.")
            return

        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["tenant_group"]:
            if global_settings["tenant_group"] is not None:  # noqa: F821
                for bs_tenant_group in global_settings["tenant_group"]:  # noqa: F821
                    self.load_tenant_group(bs_tenant_group=bs_tenant_group, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["tenant"]:
            if global_settings["tenant"] is not None:  # noqa: F821
                for bs_tenant in global_settings["tenant"]:  # noqa: F821
                    self.load_tenant(bs_tenant=bs_tenant, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["role"]:
            if global_settings["role"] is not None:  # noqa: F821
                for bs_role in global_settings["role"]:  # noqa: F821
                    self.load_role(bs_role=bs_role, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["manufacturer"]:
            if global_settings["manufacturer"] is not None:  # noqa: F821
                for bs_manufacturer in global_settings["manufacturer"]:  # noqa: F821
                    self.load_manufacturer(bs_manufacturer=bs_manufacturer, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["platform"]:
            if global_settings["platform"] is not None:  # noqa: F821
                for bs_platform in global_settings["platform"]:  # noqa: F821
                    self.load_platform(bs_platform=bs_platform, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["location_type"]:
            if global_settings["location_type"] is not None:  # noqa: F821
                for bs_location_type in global_settings["location_type"]:  # noqa: F821
                    self.load_location_type(bs_location_type=bs_location_type, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["location"]:
            if global_settings["location"] is not None:  # noqa: F821
                for bs_location in global_settings["location"]:  # noqa: F821
                    self.load_location(bs_location=bs_location, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["team"]:
            if global_settings["team"] is not None:  # noqa: F821
                for bs_team in global_settings["team"]:  # noqa: F821
                    self.load_team(bs_team=bs_team, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["contact"]:
            if global_settings["contact"] is not None:  # noqa: F821
                for bs_contact in global_settings["contact"]:  # noqa: F821
                    self.load_contact(bs_contact=bs_contact, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["provider"]:
            if global_settings["provider"] is not None:  # noqa: F821
                for bs_provider in global_settings["provider"]:  # noqa: F821
                    self.load_provider(bs_provider=bs_provider, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["provider_network"]:
            if global_settings["provider_network"] is not None:  # noqa: F821
                for bs_provider_network in global_settings["provider_network"]:  # noqa: F821
                    self.load_provider_network(bs_provider_network=bs_provider_network, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["circuit_type"]:
            if global_settings["circuit_type"] is not None:  # noqa: F821
                for bs_circuit_type in global_settings["circuit_type"]:  # noqa: F821
                    self.load_circuit_type(bs_circuit_type=bs_circuit_type, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["circuit"]:
            if global_settings["circuit"] is not None:  # noqa: F821
                for bs_circuit in global_settings["circuit"]:  # noqa: F821
                    self.load_circuit(bs_circuit=bs_circuit, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["circuit_termination"]:
            if global_settings["circuit_termination"] is not None:  # noqa: F821
                for bs_circuit_termination in global_settings["circuit_termination"]:  # noqa: F821
                    self.load_circuit_termination(
                        bs_circuit_termination=bs_circuit_termination,
                        branch_vars=branch_vars,
                    )
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["namespace"]:
            if global_settings["namespace"] is not None:  # noqa: F821
                for bs_namespace in global_settings["namespace"]:  # noqa: F821
                    self.load_namespace(bs_namespace=bs_namespace, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["rir"]:
            if global_settings["rir"] is not None:  # noqa: F821
                for bs_rir in global_settings["rir"]:  # noqa: F821
                    self.load_rir(bs_rir=bs_rir, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["vlan_group"]:
            if global_settings["vlan_group"] is not None:  # noqa: F821
                for bs_vlan_group in global_settings["vlan_group"]:  # noqa: F821
                    self.load_vlan_group(bs_vlan_group=bs_vlan_group, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["vlan"]:
            if global_settings["vlan"] is not None:  # noqa: F821
                for bs_vlan in global_settings["vlan"]:  # noqa: F821
                    self.load_vlan(bs_vlan=bs_vlan, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["vrf"]:
            if global_settings["vrf"] is not None:  # noqa: F821
                for bs_vrf in global_settings["vrf"]:  # noqa: F821
                    self.load_vrf(bs_vrf=bs_vrf, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["prefix"]:
            if global_settings["prefix"] is not None:  # noqa: F821
                for bs_prefix in global_settings["prefix"]:  # noqa: F821
                    self.load_prefix(bs_prefix=bs_prefix, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["secret"]:
            if global_settings["secret"] is not None:  # noqa: F821
                for bs_secret in global_settings["secret"]:  # noqa: F821
                    self.load_secret(bs_secret=bs_secret, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["secrets_group"]:
            if global_settings["secrets_group"] is not None:  # noqa: F821
                for bs_sg in global_settings["secrets_group"]:  # noqa: F821
                    self.load_secrets_group(bs_sg=bs_sg, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["git_repository"]:
            if global_settings["git_repository"] is not None:  # noqa: F821
                for git_repo in global_settings["git_repository"]:  # noqa: F821
                    self.load_git_repository(git_repo=git_repo, branch_vars=branch_vars)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["dynamic_group"]:
            if global_settings["dynamic_group"] is not None:  # noqa: F821
                for dyn_group in global_settings["dynamic_group"]:  # noqa: F821
                    self.load_dynamic_group(dyn_group=dyn_group)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["computed_field"]:
            if global_settings["computed_field"] is not None:  # noqa: F821
                for computed_field in global_settings["computed_field"]:  # noqa: F821
                    self.load_computed_field(comp_field=computed_field)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["tag"]:
            if global_settings["tag"] is not None:  # noqa: F821
                for tag in global_settings["tag"]:  # noqa: F821
                    self.load_tag(tag=tag)
        if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["graph_ql_query"]:
            if global_settings["graph_ql_query"] is not None:  # noqa F821
                for graph_ql_query in global_settings["graph_ql_query"]:  # noqa F821
                    self.load_graph_ql_query(query=graph_ql_query)
        if LIFECYCLE_MGMT:
            if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["software"]:
                for software in global_settings["software"]:  # noqa: F821
                    self.load_software(software=software)
            if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["software_image"]:
                for software_image in global_settings["software_image"]:  # noqa: F821
                    self.load_software_image(software_image=software_image)
            if settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]["validated_software"]:
                for validated_software in global_settings["validated_software"]:  # noqa: F821
                    self.load_validated_software(validated_software=validated_software)
