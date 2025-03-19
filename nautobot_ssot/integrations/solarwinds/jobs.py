# pylint: disable=R0801
"""Jobs for SolarWinds SSoT integration."""

from diffsync.enum import DiffSyncFlags
from django.urls import reverse
from nautobot.apps.jobs import BooleanVar, ChoiceVar, JSONVar, ObjectVar, StringVar, TextVar, register_jobs
from nautobot.dcim.models import Device, Location, LocationType
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import ExternalIntegration, Role
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.solarwinds.diffsync.adapters import nautobot, solarwinds
from nautobot_ssot.integrations.solarwinds.utils.solarwinds import SolarWindsClient
from nautobot_ssot.jobs.base import DataMapping, DataSource

name = "SolarWinds SSoT"  # pylint: disable=invalid-name


ROLE_CHOICES = (("DeviceType", "DeviceType"), ("Hostname", "Hostname"))
PULL_FROM_CHOICES = (("Containers", "Containers"), ("CustomProperty", "Custom Property"))


class JobConfigError(Exception):
    """Custom Exception for misconfigured Job form."""


class SolarWindsDataSource(DataSource):  # pylint: disable=too-many-instance-attributes
    """SolarWinds SSoT Data Source."""

    integration = ObjectVar(
        model=ExternalIntegration,
        queryset=ExternalIntegration.objects.all(),
        display_field="display",
        label="SolarWinds Instance",
        required=True,
    )
    custom_property = StringVar(
        description="Name of SolarWinds Custom Property existing (set to True) on Devices to be synced.",
        label="SolarWinds Custom Property",
        required=False,
    )
    location_override = ObjectVar(
        model=Location,
        queryset=Location.objects.all(),
        description="Override using Container names for Location, all devices synced will be placed here.",
        label="Location Override",
        required=False,
    )
    containers = TextVar(
        default="ALL",
        description="Comma separated list of Containers to be Imported. Use 'ALL' to import every container from SolarWinds. Must specify Top Container if `ALL` is specified, unless using CustomProperty.",
        label="Container(s)",
        required=True,
    )
    top_container = TextVar(
        default="",
        description="Top-level Container if `ALL` containers are to be imported.",
        label="Top Container",
        required=False,
    )
    location_type = ObjectVar(
        model=LocationType,
        queryset=LocationType.objects.all(),
        description="LocationType to define Container(s) as. Must support Device ContentType.",
        label="Location Type",
        required=False,
    )
    parent = ObjectVar(
        model=Location,
        queryset=Location.objects.all(),
        description="Parent Location to assign created Containers to if specified LocationType requires parent be defined.",
        label="Parent Location",
        required=False,
    )
    tenant = ObjectVar(
        model=Tenant,
        queryset=Tenant.objects.all(),
        description="Tenant to assign to imported Devices.",
        label="Tenant",
        required=False,
    )
    role_map = JSONVar(
        label="Device Roles Map", description="Mapping of matching object to Role.", default={}, required=False
    )
    role_choice = ChoiceVar(
        choices=ROLE_CHOICES,
        label="Role Map Matching Attribute",
        description="Specify which Device attribute to match for Role Map.",
    )
    default_role = ObjectVar(
        label="Default Device Role",
        model=Role,
        queryset=Role.objects.all(),
        query_params={"content_types": Device._meta.label_lower},
        display_field="name",
        required=True,
    )
    debug = BooleanVar(description="Enable for more verbose debug logging", default=False)

    def __init__(self):
        """Initialize job objects."""
        super().__init__()
        self.data = None
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta data for SolarWinds."""

        name = "SolarWinds to Nautobot"
        data_source = "SolarWinds"
        data_target = "Nautobot"
        description = "Sync information from SolarWinds to Nautobot"
        has_sensitive_variables = False
        field_order = [
            "dryrun",
            "debug",
            "integration",
            "location_type",
            "custom_property",
            "containers",
            "top_container",
            "location_override",
            "parent",
            "tenant",
            "default_role",
            "role_choice",
            "role_map",
        ]

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {}

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping("Containers", None, "Locations", reverse("dcim:location_list")),
            DataMapping("Devices", None, "Devices", reverse("dcim:device_list")),
            DataMapping("Interfaces", None, "Interfaces", reverse("dcim:interface_list")),
            DataMapping("Prefixes", None, "Prefixes", reverse("ipam:prefix_list")),
            DataMapping("IP Addresses", None, "IP Addresses", reverse("ipam:ipaddress_list")),
            DataMapping("Vendor", None, "Manufacturers", reverse("dcim:manufacturer_list")),
            DataMapping("Model/DeviceType", None, "DeviceTypes", reverse("dcim:devicetype_list")),
            DataMapping("Model/Vendor", None, "Platforms", reverse("dcim:platform_list")),
            DataMapping("OS Version", None, "SoftwareVersions", reverse("dcim:softwareversion_list")),
        )

    def validate_containers(self):
        """Confirm Job form variable for containers."""
        if self.containers == "":
            self.logger.error("Containers variable must be defined with container name(s) or 'ALL'.")
            raise JobConfigError
        if self.containers == "ALL" and self.top_container == "":
            self.logger.error("Top Container must be specified if `ALL` Containers are to be imported.")
            raise JobConfigError

    def validate_location_configuration(self):
        """Confirm that LocationType or Location Override are set properly."""
        if not self.location_type:
            if not self.location_override:
                self.logger.error("A Location Type must be specified, unless using Location Override.")
                raise JobConfigError
            return

        if self.location_type.parent is not None and self.parent is None:
            self.logger.error("LocationType %s requires Parent Location be specified.", self.location_type)
            raise JobConfigError
        if self.location_type.parent is None and self.parent:
            self.logger.error(
                "LocationType %s does not require a Parent location, but a Parent location was chosen.",
                self.location_type,
            )
            raise JobConfigError

        if ("dcim", "device") not in self.location_type.content_types.values_list("app_label", "model"):
            self.logger.error(
                "Specified LocationType %s is missing Device ContentType. Please change LocationType or add Device ContentType to %s LocationType and re-run Job.",
                self.location_type,
                self.location_type,
            )
            raise JobConfigError

    def validate_role_map(self):
        """Confirm configuration of Role Map Job var."""
        if self.role_map and not self.role_choice:
            self.logger.error("Role Map Matching Attribute must be defined if Role Map is specified.")
            raise JobConfigError

    def load_source_adapter(self):
        """Load data from SolarWinds into DiffSync models."""
        self.validate_containers()
        self.validate_location_configuration()
        _sg = self.integration.secrets_group
        username = _sg.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
        )
        password = _sg.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
        )
        port = self.integration.extra_config.get("port") if self.integration.extra_config else None
        retries = self.integration.extra_config.get("retries") if self.integration.extra_config else None
        client = SolarWindsClient(
            hostname=self.integration.remote_url,
            username=username,
            password=password,
            port=port if port else 17774,
            retries=retries if retries else 5,
            timeout=self.integration.timeout,
            verify=self.integration.verify_ssl,
            job=self,
        )
        self.source_adapter = solarwinds.SolarWindsAdapter(
            job=self,
            sync=self.sync,
            client=client,
            containers=self.containers,
            location_type=self.location_type,
            parent=self.parent,
            tenant=self.tenant,
        )
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.target_adapter = nautobot.NautobotAdapter(job=self, sync=self.sync)
        self.target_adapter.load()

    def run(  # pylint: disable=arguments-differ, too-many-arguments
        self,
        integration,
        containers,
        top_container,
        dryrun,
        location_type,
        parent,
        tenant,
        role_map,
        role_choice,
        default_role,
        memory_profiling,
        debug,
        *args,
        **kwargs,
    ):
        """Perform data synchronization."""
        self.integration = integration
        self.custom_property = kwargs["custom_property"]
        self.location_override = kwargs["location_override"]
        self.containers = containers
        self.top_container = top_container
        self.location_type = (
            location_type if location_type else self.location_override.location_type if self.location_override else None
        )
        self.parent = parent
        self.tenant = tenant
        self.role_map = role_map
        self.role_choice = role_choice
        self.default_role = default_role
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [SolarWindsDataSource]
register_jobs(*jobs)
