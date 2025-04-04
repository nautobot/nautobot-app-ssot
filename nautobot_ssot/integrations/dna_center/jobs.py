"""Jobs for DNA Center SSoT integration."""

from ast import literal_eval

from diffsync.enum import DiffSyncFlags
from django.templatetags.static import static
from django.urls import reverse
from nautobot.apps.jobs import BooleanVar, JSONVar, ObjectVar, StringVar
from nautobot.core.celery import register_jobs
from nautobot.dcim.models import Controller, LocationType
from nautobot.extras.choices import (
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)
from nautobot.tenancy.models import Tenant

from nautobot_ssot.exceptions import ConfigurationError
from nautobot_ssot.integrations.dna_center.diffsync.adapters import dna_center, nautobot
from nautobot_ssot.integrations.dna_center.utils.dna_center import DnaCenterClient
from nautobot_ssot.jobs.base import DataMapping, DataSource
from nautobot_ssot.utils import verify_controller_managed_device_group

name = "DNA Center SSoT"  # pylint: disable=invalid-name


class DnaCenterDataSource(DataSource):  # pylint: disable=too-many-instance-attributes
    """DNA Center SSoT Data Source."""

    dnac = ObjectVar(
        model=Controller,
        queryset=Controller.objects.all(),
        display_field="display",
        required=True,
        label="DNA Center Controller",
    )
    area_loctype = ObjectVar(
        model=LocationType,
        queryset=LocationType.objects.all(),
        display_field="display",
        required=True,
        label="Area LocationType",
        description="LocationType to use for imported DNA Center Areas. Must allow nesting.",
    )
    building_loctype = ObjectVar(
        model=LocationType,
        queryset=LocationType.objects.all(),
        display_field="display",
        required=True,
        label="Building LocationType",
        description="LocationType to use for imported DNA Center Buildings.",
    )
    floor_loctype = ObjectVar(
        model=LocationType,
        queryset=LocationType.objects.all(),
        display_field="display",
        required=True,
        label="Floor LocationType",
        description="LocationType to use for imported DNA Center Floors.",
    )
    location_map = JSONVar(
        label="Location Mapping",
        required=False,
        default={},
        description="Map of information regarding Locations in DNA Center. Ex: {'<Location Name>': {'parent': '<Parent location Name>'}}",
    )
    hostname_map = StringVar(
        default=[],
        description="List of tuples containing Device hostnames to assign to specified Role. ex: [('core-router.com', 'router')]",
        label="Hostname Mapping",
        required=False,
    )

    debug = BooleanVar(description="Enable for more verbose debug logging", default=False)
    bulk_import = BooleanVar(
        description="Perform bulk operations when importing data. CAUTION! Might cause bad data to be pushed to Nautobot.",
        default=False,
    )
    tenant = ObjectVar(model=Tenant, label="Tenant", required=False)

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta data for DNA Center."""

        name = "DNA Center to Nautobot"
        data_source = "DNA Center"
        data_target = "Nautobot"
        description = "Sync information from DNA Center to Nautobot"
        data_source_icon = static("nautobot_ssot_dna_center/dna_center_logo.png")
        has_sensitive_variables = False
        field_order = [
            "dryrun",
            "bulk_import",
            "debug",
            "dnac",
            "area_loctype",
            "building_loctype",
            "floor_loctype",
            "location_map",
            "hostname_map",
            "tenant",
        ]

    def __init__(self):
        """Initiailize Job vars."""
        super().__init__()
        self.controller_group = None
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {"Instances": "Found in Extensibility -> External Integrations menu."}

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping("Areas", None, "Locations", reverse("dcim:location_list")),
            DataMapping("Buildings", None, "Locations", reverse("dcim:location_list")),
            DataMapping("Floors", None, "Locations", reverse("dcim:location_list")),
            DataMapping("Devices", None, "Devices", reverse("dcim:device_list")),
            DataMapping("Interfaces", None, "Interfaces", reverse("dcim:interface_list")),
            DataMapping("IP Addresses", None, "IP Addresses", reverse("ipam:ipaddress_list")),
        )

    def load_source_adapter(self):
        """Load data from DNA Center into DiffSync models."""
        self.logger.info(f"Loading data from {self.dnac.name}")
        self.controller_group = verify_controller_managed_device_group(controller=self.dnac)
        _sg = self.dnac.external_integration.secrets_group
        username = _sg.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
        )
        password = _sg.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
        )
        client = DnaCenterClient(
            url=self.dnac.external_integration.remote_url,
            username=username,
            password=password,
            port=(
                self.dnac.external_integration.extra_config.get("port", 443)
                if getattr(self.dnac.external_integration, "extra_config")
                else 443
            ),
            verify=self.dnac.external_integration.verify_ssl,
        )
        client.connect()
        self.source_adapter = dna_center.DnaCenterAdapter(job=self, sync=self.sync, client=client, tenant=self.tenant)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.target_adapter = nautobot.NautobotAdapter(job=self, sync=self.sync, tenant=self.tenant)
        self.target_adapter.load()

    def validate_locationtypes(self):
        """Validate the LocationTypes specified are related and configured correctly."""
        if not self.area_loctype.nestable:
            self.logger.error("Area LocationType is not nestable.")
            raise ConfigurationError(f"{self.area_loctype.name} LocationType is not nestable.")
        if self.building_loctype.parent != self.area_loctype:
            self.logger.error(
                "LocationType %s is not the parent of %s LocationType. The Area and Building LocationTypes specified must be related.",
                self.area_loctype.name,
                self.building_loctype.name,
            )
            raise ConfigurationError(
                f"{self.area_loctype.name} is not parent to {self.building_loctype.name}. Please correct.",
            )
        if self.floor_loctype.parent != self.building_loctype:
            self.logger.error(
                "LocationType %s is not the parent of %s LocationType. The Building and Floor LocationTypes specified must be related.",
                self.building_loctype.name,
                self.floor_loctype.name,
            )
            raise ConfigurationError(
                f"{self.building_loctype.name} is not parent to {self.floor_loctype.name}. Please correct.",
            )

    def run(
        self,
        dryrun,
        memory_profiling,
        debug,
        dnac,
        area_loctype,
        building_loctype,
        floor_loctype,
        location_map,
        hostname_map,
        bulk_import,
        tenant,
        *args,
        **kwargs,  # pylint: disable=arguments-differ, too-many-arguments
    ):
        """Perform data synchronization."""
        self.dnac = dnac
        self.area_loctype = area_loctype
        self.building_loctype = building_loctype
        self.floor_loctype = floor_loctype
        self.validate_locationtypes()
        self.location_map = location_map
        self.hostname_map = literal_eval(hostname_map)
        self.tenant = tenant
        self.debug = debug
        self.bulk_import = bulk_import
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [DnaCenterDataSource]
register_jobs(*jobs)
