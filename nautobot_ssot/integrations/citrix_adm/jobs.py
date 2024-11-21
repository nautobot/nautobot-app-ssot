"""Jobs for Citrix ADM SSoT integration."""

from ast import literal_eval

from diffsync.enum import DiffSyncFlags
from django.templatetags.static import static
from django.urls import reverse
from nautobot.core.celery import register_jobs
from nautobot.dcim.models import Location, LocationType
from nautobot.extras.jobs import BooleanVar, Job, JSONVar, MultiObjectVar, ObjectVar, StringVar
from nautobot.extras.models import ExternalIntegration
from nautobot.tenancy.models import Tenant

from nautobot_ssot.exceptions import JobException
from nautobot_ssot.integrations.citrix_adm.diffsync.adapters import citrix_adm, nautobot
from nautobot_ssot.jobs.base import DataMapping, DataSource, DataTarget

name = "Citrix ADM SSoT"  # pylint: disable=invalid-name


class CitrixAdmDataSource(DataSource, Job):  # pylint: disable=too-many-instance-attributes
    """Citrix ADM SSoT Data Source."""

    instances = MultiObjectVar(
        model=ExternalIntegration,
        queryset=ExternalIntegration.objects.all(),
        display_field="display",
        label="Citrix ADM Instances",
        required=True,
    )
    dc_loctype = ObjectVar(
        model=LocationType,
        queryset=LocationType.objects.all(),
        query_params={"content_types": "dcim.device"},
        display_field="display",
        label="Datacenter LocationType",
        description="LocationType to use when importing Datacenters from Citrix ADM. Must have Device ContentType.",
        required=True,
    )
    parent_location = ObjectVar(
        model=Location,
        queryset=Location.objects.all(),
        query_params={"location_type": "$dc_loctype.parent"},
        display_field="display",
        label="Parent Location",
        description="Parent Location to assign to imported Datacenters. Required if parent is specified on Datacenter LocationType.",
        required=False,
    )
    location_map = JSONVar(
        label="Location Map",
        description="Mapping of Datacenter name to parent and name. Ex: {'US': {'name': 'United States', 'parent': 'North America'}}.",
        default={},
        required=False,
    )
    hostname_mapping = StringVar(
        label="Hostname Mapping",
        description="List of tuples containing Device hostname regex patterns to assign to specified Role. ex: [('.*ilb.*', 'Internal Load-Balancer')]",
        default=[],
        required=False,
    )
    tenant = ObjectVar(model=Tenant, queryset=Tenant.objects.all(), display_field="display_name", required=False)
    debug = BooleanVar(description="Enable for more verbose debug logging", default=False)

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta data for Citrix ADM."""

        name = "Citrix ADM to Nautobot"
        data_source = "Citrix ADM"
        data_target = "Nautobot"
        data_source_icon = static("nautobot_ssot_citrix_adm/citrix_logo.png")
        description = "Sync information from Citrix ADM to Nautobot"
        field_order = [
            "dryrun",
            "debug",
            "instances",
            "dc_loctype",
            "parent_location",
            "location_map",
            "hostname_mapping",
            "tenant",
        ]

    def __init__(self):
        """Initialize job objects."""
        super().__init__()
        self.data = None
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {}

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping("Datacenters", None, "Locations", reverse("dcim:location_list")),
            DataMapping("Devices", None, "Devices", reverse("dcim:device_list")),
            DataMapping("Ports", None, "Interfaces", reverse("dcim:interface_list")),
            DataMapping("Prefixes", None, "Prefixes", reverse("ipam:prefix_list")),
            DataMapping("IP Addresses", None, "IP Addresses", reverse("ipam:ipaddress_list")),
        )

    def load_source_adapter(self):
        """Load data from Citrix ADM into DiffSync models."""
        self.source_adapter = citrix_adm.CitrixAdmAdapter(
            job=self, sync=self.sync, instances=self.instances, tenant=self.tenant
        )
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.target_adapter = nautobot.NautobotAdapter(job=self, sync=self.sync, tenant=self.tenant)
        self.target_adapter.load()

    def validate_job_settings(self):
        """Validate the settings defined in the Job form are correct."""
        if (
            self.dc_loctype.parent
            and not self.parent_location
            and (self.location_map and not all(bool("parent" in value) for value in self.location_map.values()))
        ):
            self.logger.error(
                f"{self.dc_loctype.name} requires a parent Location and you've not specified a parent Location. Please review your Job settings."
            )
            raise JobException(message=f"Parent Location is required for {self.dc_loctype.name} LocationType.")

    def run(  # pylint: disable=arguments-differ, too-many-arguments
        self, dryrun, memory_profiling, instances, tenant, debug, *args, **kwargs
    ):
        """Perform data synchronization."""
        self.instances = instances
        self.tenant = tenant
        self.debug = debug
        self.dryrun = dryrun
        self.dc_loctype = kwargs["dc_loctype"]
        self.parent_location = kwargs["parent_location"]
        self.location_map = kwargs["location_map"]
        self.hostname_mapping = literal_eval(kwargs["hostname_mapping"])
        self.validate_job_settings()
        self.memory_profiling = memory_profiling
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


class CitrixAdmDataTarget(DataTarget, Job):
    """Citrix ADM SSoT Data Target."""

    instance = ObjectVar(
        model=ExternalIntegration,
        queryset=ExternalIntegration.objects.all(),
        display_field="display",
        label="Citrix ADM Instance",
        required=True,
    )
    tenant = ObjectVar(model=Tenant, queryset=Tenant.objects.all(), display_field="display_name", required=False)
    debug = BooleanVar(description="Enable for more verbose debug logging", default=False)

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta data for Citrix ADM."""

        name = "Nautobot to Citrix ADM"
        data_source = "Nautobot"
        data_target = "Citrix ADM"
        description = "Sync information from Nautobot to Citrix ADM"

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
        self.source_adapter = nautobot.NautobotAdapter(job=self, sync=self.sync, tenant=self.tenant)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Citrix ADM into DiffSync models."""
        self.target_adapter = citrix_adm.CitrixAdmAdapter(
            job=self, sync=self.sync, instances=self.instance, tenant=self.tenant
        )
        self.target_adapter.load()

    def run(  # pylint: disable=arguments-differ, too-many-arguments
        self, dryrun, memory_profiling, instance, tenant, debug, *args, **kwargs
    ):
        """Perform data synchronization."""
        self.instance = instance
        self.tenant = tenant
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [CitrixAdmDataSource]
register_jobs(*jobs)
