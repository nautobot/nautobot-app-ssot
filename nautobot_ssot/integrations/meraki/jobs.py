"""Jobs for Meraki SSoT integration."""

from ast import literal_eval

from diffsync.enum import DiffSyncFlags
from django.urls import reverse
from nautobot.core.celery import register_jobs
from nautobot.dcim.models import Controller, Location, LocationType
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.jobs import BooleanVar, JSONVar, ObjectVar, StringVar
from nautobot.tenancy.models import Tenant

from nautobot_ssot.exceptions import JobException
from nautobot_ssot.integrations.meraki.diffsync.adapters import meraki, nautobot
from nautobot_ssot.integrations.meraki.utils.meraki import DashboardClient
from nautobot_ssot.jobs.base import DataMapping, DataSource
from nautobot_ssot.utils import verify_controller_managed_device_group

name = "Meraki SSoT"  # pylint: disable=invalid-name


class MerakiDataSource(DataSource):  # pylint: disable=too-many-instance-attributes
    """Meraki SSoT Data Source."""

    instance = ObjectVar(
        model=Controller,
        queryset=Controller.objects.all(),
        description="Controller with ExternalIntegration containing information for connecting to Meraki dashboard.",
        display_field="display",
        label="Meraki Controller",
        required=True,
    )
    network_loctype = ObjectVar(
        model=LocationType,
        queryset=LocationType.objects.all(),
        description="LocationType to use for imported Networks.",
        display_field="display",
        label="Network LocationType",
        required=True,
    )
    parent_location = ObjectVar(
        model=Location,
        queryset=Location.objects.all(),
        query_params={"location_type": "$network_loctype.parent"},
        description="Default parent Location to assign imported Networks as.",
        display_field="display",
        label="Parent Location",
        required=False,
    )
    location_map = JSONVar(
        label="Location Mapping",
        required=False,
        default={},
        description="Map of information regarding Networks in Meraki and their parent Location(s).",
    )
    hostname_mapping = StringVar(
        label="Hostname Mapping",
        required=False,
        default=[],
        description="List of tuples containing Device hostnames to assign to specified Role. ex: [('core-router.com', 'router')]",
    )
    devicetype_mapping = StringVar(
        label="DeviceType Mapping",
        required=False,
        default=[],
        description="List of tuples containing DeviceTypes to assign to a specified Role. ex: [('MX', 'Firewall')]",
    )
    debug = BooleanVar(description="Enable for more verbose debug logging", default=False)
    tenant = ObjectVar(model=Tenant, label="Tenant", required=False)

    def __init__(self):
        """Initialize job objects."""
        super().__init__()
        self.data = None
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta data for Meraki."""

        name = "Meraki => Nautobot"
        data_source = "Meraki"
        data_target = "Nautobot"
        description = "Sync information from Meraki to Nautobot"
        field_order = [
            "dryrun",
            "debug",
            "instance",
            "network_loctype",
            "parent_location",
            "location_map",
            "hostname_mapping",
            "devicetype_mapping",
            "tenant",
        ]

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {}

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping("Networks", None, "Locations", reverse("dcim:location_list")),
            DataMapping("Devices", None, "Devices", reverse("dcim:device_list")),
            DataMapping("Ports", None, "Interfaces", reverse("dcim:interface_list")),
            DataMapping("Prefixes", None, "Prefixes", reverse("ipam:prefix_list")),
            DataMapping("IP Addresses", None, "IP Addresses", reverse("ipam:ipaddress_list")),
        )

    def validate_settings(self):
        """Confirm the settings in the Job form are valid."""
        if self.network_loctype.parent and (
            not self.parent_location
            and (not self.location_map or not all("parent" in value for value in self.location_map.values()))
        ):
            network_loctype = self.network_loctype.name
            self.logger.error(
                f"{network_loctype} requires a parent Location be provided when creating {network_loctype} Locations and the Parent Location and Location Mapping fields are undefined."
            )
            raise JobException(message="Parent Location is required but undefined in Job form.")

    def load_source_adapter(self):
        """Load data from Meraki into DiffSync models."""
        verify_controller_managed_device_group(controller=self.instance)
        self.validate_settings()
        _sg = self.instance.external_integration.secrets_group
        org_id = _sg.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
        )
        token = _sg.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
        )
        client = DashboardClient(logger=self, org_id=org_id, token=token)
        self.source_adapter = meraki.MerakiAdapter(job=self, sync=self.sync, client=client, tenant=self.tenant)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.target_adapter = nautobot.NautobotAdapter(job=self, sync=self.sync, tenant=self.tenant)
        self.target_adapter.load()

    def run(
        self,
        dryrun,
        memory_profiling,
        debug,
        *args,
        **kwargs,
    ):  # pylint: disable=arguments-differ
        """Perform data synchronization."""
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        self.instance = kwargs["instance"]
        self.network_loctype = kwargs["network_loctype"]
        self.parent_location = kwargs["parent_location"]
        self.location_map = kwargs["location_map"]
        self.debug = debug
        self.tenant = kwargs["tenant"]
        self.hostname_mapping = literal_eval(kwargs["hostname_mapping"])
        self.devicetype_mapping = literal_eval(kwargs["devicetype_mapping"])
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [MerakiDataSource]
register_jobs(*jobs)
