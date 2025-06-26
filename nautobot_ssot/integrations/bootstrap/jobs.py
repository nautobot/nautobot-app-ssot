"""Jobs for bootstrap SSoT integration."""

import os

from nautobot.apps.jobs import BooleanVar, ChoiceVar

from nautobot_ssot.integrations.bootstrap.diffsync.adapters import bootstrap, nautobot
from nautobot_ssot.jobs.base import DataMapping, DataSource, DataTarget
from nautobot_ssot.utils import core_supports_softwareversion, dlm_supports_softwarelcm, validate_dlm_installed

name = "Bootstrap SSoT"  # pylint: disable=invalid-name


class BootstrapDataSource(DataSource):
    """Bootstrap SSoT Data Source."""

    debug = BooleanVar(description="Enable for more verbose debug logging", default=False)
    load_source = ChoiceVar(
        choices=(
            ("file", "File"),
            ("git", "Git"),
            ("env_var", "Environment Variable"),
        ),
        description="Where to load the yaml files from",
        label="Load Source",
        default="env_var",
    )

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta data for bootstrap."""

        name = "Bootstrap to Nautobot"
        data_source = "Bootstrap"
        data_target = "Nautobot"
        description = "Sync information from Bootstrap to Nautobot"

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {
            "Git loading source": os.getenv("NAUTOBOT_BOOTSTRAP_SSOT_LOAD_SOURCE"),
            "Git branch": os.getenv("NAUTOBOT_BOOTSTRAP_SSOT_ENVIRONMENT_BRANCH"),
        }

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        data_mappings = [
            DataMapping("tenant_group", "", "TenantGroup", "tenancy:tenant-groups"),
            DataMapping("tenant", "", "Tenant", "tenancy:tenant"),
            DataMapping("role", "", "Roles", "extras.roles"),
            DataMapping("manufacturer", "", "Manufacturer", "dcim.manufacturer"),
            DataMapping("platform", "", "Platform", "dcim.platform"),
            DataMapping("location_type", "", "LocationType", "dcim.location-type"),
            DataMapping("location", "", "Location", "dcim.location"),
            DataMapping("secrets", "", "Secrets", "extras:secrets"),
            DataMapping("secrets_groups", "", "SecretsGroup", "extras:secrets-groups"),
            DataMapping("git_repositories", "", "GitRepository", "extras:git-repositories"),
            DataMapping("dynamic_groups", "", "DynamicGroup", "extras:dynamic-groups"),
            DataMapping("computed_field", "", "ComputedField", "extras:computed-field"),
            DataMapping("tags", "", "Tag", "extras.tag"),
            DataMapping("graphql_query", "", "GraphQLQuery", "extras:graphql-query"),
            DataMapping("tenant_group", "", "TenantGroup", "tenancy:tenant-troup"),
            DataMapping("tenant", "", "Tenant", "tenancy:tenant"),
            DataMapping("role", "", "Role", "extras:role"),
            DataMapping("manufacturer", "", "Manufacturer", "dcim.manufacturer"),
            DataMapping("platform", "", "Platform", "dcim.platform"),
            DataMapping("location_type", "", "LocationType", "dcim.location_type"),
            DataMapping("location", "", "Location", "dcim.location"),
            DataMapping("team", "", "Team", "extras.team"),
            DataMapping("contact", "", "Contact", "extras.contact"),
            DataMapping("provider", "", "Provider", "circuits.provider"),
            DataMapping("provider_network", "", "ProviderNetwork", "circuits.provider_network"),
            DataMapping("circuit_type", "", "CircuitType", "circuits.circuit_type"),
            DataMapping("circuit", "", "Circuit", "circuits.circuit"),
            DataMapping(
                "circuit_termination",
                "",
                "CircuitTermination",
                "circuits.circuit_termination",
            ),
            DataMapping("namespace", "", "Namespace", "ipam.namespcae"),
            DataMapping("rir", "", "RIR", "ipam.rir"),
            DataMapping("vlan_group", "", "VLANGroup", "ipam.vlan_group"),
            DataMapping("vlan", "", "VLAN", "ipam.vlan"),
            DataMapping("vrf", "", "VRF", "ipam.vrf"),
            DataMapping("prefix", "", "Prefix", "ipam.prefix"),
        ]
        if core_supports_softwareversion():
            data_mappings.append(DataMapping("software_image", "", "SoftwareImageFile", "dcim:software-image-file"))
            data_mappings.append(DataMapping("software", "", "SoftwareVersion", "dcim:software-version"))
            if validate_dlm_installed():
                data_mappings.append(
                    DataMapping("validated_software", "", "ValidatedSoftware", "extras:validated-software")
                )
        elif dlm_supports_softwarelcm():
            data_mappings.append(DataMapping("software_image", "", "SoftwareImage", "extras:software-image"))
            data_mappings.append(DataMapping("software", "", "Software", "extras:software"))
            data_mappings.append(
                DataMapping("validated_software", "", "ValidatedSoftware", "extras:validated-software")
            )

        return data_mappings

    def load_source_adapter(self):
        """Load data from Bootstrap into DiffSync models."""
        self.source_adapter = bootstrap.BootstrapAdapter(job=self, sync=self.sync)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.target_adapter = nautobot.NautobotAdapter(job=self, sync=self.sync)
        self.target_adapter.load()

    def run(self, load_source, dryrun, memory_profiling, debug, *args, **kwargs):  # pylint: disable=arguments-differ
        """Perform data synchronization."""
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        self.load_source = load_source
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


class BootstrapDataTarget(DataTarget):
    """bootstrap SSoT Data Target."""

    debug = BooleanVar(description="Enable for more verbose debug logging", default=False)
    read_destination = ChoiceVar(
        choices=(
            ("file", "File"),
            ("git", "Git"),
            ("env_var", "Environment Variable"),
        ),
        description="Where to load the YAML files from",
        label="Load Source",
        default="env_var",
    )

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta data for Bootstrap."""

        name = "Nautobot to Bootstrap"
        data_source = "Nautobot"
        data_target = "Bootstrap"
        description = "Sync information from Nautobot to bootstrap"

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataTarget."""
        return {}

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return ()

    def load_source_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.source_adapter = nautobot.NautobotAdapter(job=self, sync=self.sync)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Bootstrap into DiffSync models."""
        self.target_adapter = bootstrap.BootstrapAdapter(job=self, sync=self.sync)
        self.target_adapter.load()

    def run(self, read_destination, dryrun, memory_profiling, debug, *args, **kwargs):  # pylint: disable=arguments-differ
        """Perform data synchronization."""
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        self.read_destination = read_destination
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [BootstrapDataSource]
