"""Jobs for LibreNMS SSoT integration."""

# pylint: disable=duplicate-code
import os
from ast import literal_eval

from django.templatetags.static import static
from django.utils import timezone
from nautobot.apps.jobs import (
    BooleanVar,
    ChoiceVar,
    Job,
    JSONVar,
    MultiObjectVar,
    ObjectVar,
    StringVar,
)
from nautobot.core.celery import register_jobs
from nautobot.dcim.models import LocationType, Platform
from nautobot.extras.choices import (
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)
from nautobot.extras.models import ExternalIntegration, Role, SecretsGroup
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.librenms.diffsync.adapters import librenms, nautobot
from nautobot_ssot.integrations.librenms.platform_consolidation import (
    COLLISION_MERGE,
    COLLISION_REFUSE,
    DEVICE_TYPE_MERGE,
    DEVICE_TYPE_REFUSE,
    MANUFACTURER_CLEAR,
    MANUFACTURER_SKIP,
    SCOPE_LIBRENMS,
    SCOPE_SELECTED,
    PlatformConsolidator,
)
from nautobot_ssot.integrations.librenms.utils.librenms import LibreNMSApi
from nautobot_ssot.jobs.base import DataMapping, DataSource, DataTarget
from nautobot_ssot.models import Sync

name = "LibreNMS SSoT"  # pylint: disable=invalid-name


class LibrenmsDataSource(DataSource):  # pylint: disable=too-many-instance-attributes
    """LibreNMS SSoT Data Source."""

    librenms_server = ObjectVar(
        model=ExternalIntegration,
        queryset=ExternalIntegration.objects.all(),
        display_field="display",
        required=False,  # We'll handle validation in the method
        label="LibreNMS Instance",
    )
    hostname_field = ChoiceVar(
        choices=(
            ("sysName", "sysName"),
            ("hostname", "Hostname"),
            ("env_var", "Environment Variable"),
        ),
        description="Which LibreNMS field to use as the name for imported device objects",
        label="Hostname Field",
        default="env_var",
    )
    location_map = JSONVar(
        label="Location Mapping.  JSON Format (ex: {'LSVG': {'name': 'Las Vegas', 'parent': 'Nevada'}})",
        required=False,
        description="Map of information regarding LibreNMS Locations and their parent Location(s).",
        default=None,
    )
    hostname_map = JSONVar(
        label="Hostname Mapping.  JSON List Format (ex: [['*.RTR.*', 'Router'], ['*.SW.*', 'Switch'], ['*.FW.*', 'Firewall']])",
        required=False,
        description="Map of information regarding LibreNMS Hostnames to Roles.",
        default=None,
    )
    default_role = ObjectVar(
        model=Role,
        queryset=Role.objects.all(),
        display_field="name",
        required=False,
        label="Default Role",
        description="Default Role to use for devices that do not have a role in the hostname map.",
        default=None,
    )
    device_secrets_group = ObjectVar(
        model=SecretsGroup,
        display_field="display",
        required=False,
        label="Device Secrets Group",
        description="Secrets Group to assign to Devices created from LibreNMS. Existing Device Secrets Group assignments are never overwritten.",
        default=None,
    )
    unpermitted_values = StringVar(
        label="Unpermitted Values",
        description="List of values that are not permitted to be imported into Hardware, Hostname, Location, OS, or Type fields. (ex: ['Router', 'Switch', 'Firewall'])",
        required=False,
        default=None,
    )
    sync_locations = BooleanVar(description="Whether to Sync Locations from LibreNMS to Nautobot.", default=False)
    location_type = ObjectVar(
        model=LocationType,
        queryset=LocationType.objects.all(),
        query_params={"content_types": "dcim.device"},
        display_field="name",
        required=False,
        label="Location Type",
        description="Location Type to use for syncing locations to LibreNMS. This should be the Location Type that actually has devices assigned. For example, Site.",
    )
    tenant = ObjectVar(
        model=Tenant,
        queryset=Tenant.objects.all(),
        description="Tenant to filter loaded information from Nautobot when syncing multiple LibreNMS Instances",
        display_field="display",
        label="Tenant Filter",
        required=False,
    )
    debug = BooleanVar(description="Enable for more verbose debug logging", default=False)

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta data for LibreNMS."""

        name = "LibreNMS to Nautobot"
        data_source = "LibreNMS"
        data_target = "Nautobot"
        description = "Sync information from LibreNMS to Nautobot"
        data_source_icon = static("nautobot_ssot_librenms/librenms.svg")
        has_sensitive_variables = False

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {
            "Instances": "Found in Extensibility -> External Integrations menu.",
            "Hostname field in use": os.getenv("NAUTOBOT_SSOT_LIBRENMS_HOSTNAME_FIELD"),
        }

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping("Geo Location", "", "Location", "dcim.location"),
            DataMapping("Device Group", "", "Tag", "extras.tags"),
            DataMapping("Device", "", "Device", "dcim.device"),
            DataMapping("Port", "", "Interface", "dcim.interfaces"),
            DataMapping("IP", "", "IPAddress", "ipam.ip_address"),
            DataMapping("VLAN", "", "VLAN", "ipam.vlan"),
            DataMapping("Manufacturer", "", "Manufacturer", "dcim.manufacturer"),
            DataMapping("DeviceType", "", "DeviceType", "dcim.device_type"),
        )

    def load_source_adapter(self):
        """Load data from LibreNMS into DiffSync models."""
        self.logger.info(f"Loading data from {self.librenms_server.name}")
        if self.librenms_server.extra_config is None or "port" not in self.librenms_server.extra_config:
            port = 443
        else:
            port = self.librenms_server.extra_config["port"]
        _sg = self.librenms_server.secrets_group
        token = _sg.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
        )
        librenms_api = LibreNMSApi(
            url=self.librenms_server.remote_url,
            port=port,
            token=token,
            verify=self.librenms_server.verify_ssl,
        )

        self.source_adapter = librenms.LibrenmsAdapter(job=self, sync=self.sync, librenms_api=librenms_api)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.target_adapter = nautobot.NautobotAdapter(job=self, sync=self.sync, tenant=self.tenant)
        self.target_adapter.load()

    def run(  # pylint: disable=too-many-arguments, too-many-locals
        self,
        dryrun,
        memory_profiling,
        debug,
        librenms_server,
        hostname_field,
        sync_locations,
        location_type,
        location_map,
        hostname_map,
        default_role,
        unpermitted_values,
        tenant,
        device_secrets_group=None,
        *args,
        **kwargs,
    ):  # pylint: disable=arguments-differ, keyword-arg-before-vararg
        """Perform data synchronization."""
        self.librenms_server = librenms_server
        self.hostname_field = hostname_field
        self.sync_locations = sync_locations
        self.location_type = location_type
        self.tenant = tenant
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        self.location_map = location_map
        self.hostname_map = hostname_map
        self.default_role = default_role
        self.device_secrets_group = device_secrets_group
        self.unpermitted_values = literal_eval(unpermitted_values)
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


class LibrenmsDataTarget(DataTarget):  # pylint: disable=too-many-instance-attributes
    """LibreNMS SSoT Data Target."""

    librenms_server = ObjectVar(
        model=ExternalIntegration,
        queryset=ExternalIntegration.objects.all(),
        display_field="display",
        required=True,
        label="LibreNMS Instance",
    )
    force_add = BooleanVar(description="Force add devices to LibreNMS (bypass ICMP check)", default=False)
    ping_fallback = BooleanVar(description="Fallback to ICMP check if device is not reachable via SNMP", default=False)
    sync_locations = BooleanVar(description="Whether to Sync Locations from Nautobot to LibreNMS.", default=False)
    location_type = ObjectVar(
        model=LocationType,
        queryset=LocationType.objects.all(),
        query_params={"content_types": "dcim.device"},
        display_field="name",
        required=False,
        label="Location Type",
        description="Location Type to use for syncing locations to LibreNMS. This should be the Location Type that actually has devices assigned. For example, Site.",
    )
    hostname_field = ""
    load_type = ""
    tenant = ObjectVar(
        model=Tenant,
        queryset=Tenant.objects.all(),
        description="Tenant to filter loaded information from Nautobot when syncing multiple LibreNMS Instances",
        display_field="display",
        label="Tenant Filter",
        required=False,
    )
    debug = BooleanVar(description="Enable for more verbose debug logging", default=False)

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta data for LibreNMS."""

        name = "Nautobot to LibreNMS"
        data_source = "Nautobot"
        data_target = "LibreNMS"
        description = "Sync information from Nautobot to LibreNMS"
        data_target_icon = static("nautobot_ssot_librenms/librenms.svg")
        has_sensitive_variables = False

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataTarget."""
        return {}

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping("dcim.location", "", "Location", "Geo Location"),
            DataMapping("extras.tags", "", "Tag", "Device Group"),
            DataMapping("dcim.device", "", "Device", "Device"),
        )

    def load_source_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.source_adapter = nautobot.NautobotAdapter(job=self, sync=self.sync, tenant=self.tenant)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from LibreNMS into DiffSync models."""
        self.logger.info(f"Loading data from {self.librenms_server.name}")
        if self.librenms_server.extra_config is None or "port" not in self.librenms_server.extra_config:
            port = 443
        else:
            port = self.librenms_server.extra_config["port"]

        _sg = self.librenms_server.secrets_group
        token = _sg.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
        )
        librenms_api = LibreNMSApi(
            url=self.librenms_server.remote_url,
            port=port,
            token=token,
            verify=self.librenms_server.verify_ssl,
        )
        self.target_adapter = librenms.LibrenmsAdapter(job=self, sync=self.sync, librenms_api=librenms_api)
        self.target_adapter.load()

    def run(self, *args, **kwargs):
        """Perform data synchronization."""
        self.librenms_server = kwargs.get("librenms_server")
        self.force_add = kwargs.get("force_add")
        self.ping_fallback = kwargs.get("ping_fallback")
        self.sync_locations = kwargs.get("sync_locations")
        self.location_type = kwargs.get("location_type")
        self.tenant = kwargs.get("tenant")
        self.debug = kwargs.get("debug")
        self.dryrun = kwargs.get("dryrun")
        self.memory_profiling = kwargs.get("memory_profiling")
        self.parallel_loading = kwargs.get("parallel_loading")
        super().run(*args, **kwargs)


class LibrenmsPlatformConsolidation(Job):  # pylint: disable=too-many-instance-attributes
    """Repair, rename and merge the Platforms the LibreNMS integration created.

    Plain Job, not DataSource/DataTarget, so get_data_jobs() keeps it off the SSoT dashboard:
    it remediates Nautobot data in place rather than syncing.
    """

    dry_run = BooleanVar(
        label="Dry run",
        description="Report what would change without writing anything. Leave enabled first.",
        default=True,
    )
    scope = ChoiceVar(
        choices=(
            (SCOPE_LIBRENMS, "LibreNMS-synced platforms"),
            (SCOPE_SELECTED, "Selected platforms"),
        ),
        label="Scope",
        description="Which Platforms this run is allowed to touch.",
        default=SCOPE_LIBRENMS,
    )
    platforms = MultiObjectVar(
        model=Platform,
        queryset=Platform.objects.all(),
        display_field="display",
        required=False,
        label="Platforms",
        description='Only used when the scope is "Selected platforms".',
    )
    repair_network_drivers = BooleanVar(
        label="Repair network drivers",
        description=(
            "Set a valid network driver on Platforms named after an Ansible collection FQCN. Changes "
            "no names and moves no devices, so this is safe in either platform-naming mode."
        ),
        default=True,
    )
    rename_legacy_platforms = BooleanVar(
        label="Rename legacy platforms",
        description=(
            "Rename cisco.ios.ios to cisco_ios, preserving the primary key. Requires "
            "librenms_consolidated_platforms to be enabled."
        ),
        default=False,
    )
    merge_duplicates = BooleanVar(
        label="Merge duplicate platforms",
        description=(
            "Collapse Platforms that share a network driver onto one survivor. Requires "
            "librenms_consolidated_platforms to be enabled."
        ),
        default=False,
    )
    software_version_collisions = ChoiceVar(
        choices=(
            (COLLISION_REFUSE, "Refuse the merge"),
            (COLLISION_MERGE, "Merge the software versions"),
        ),
        label="Software version collisions",
        description="What to do when the same version exists under both Platforms.",
        default=COLLISION_REFUSE,
    )
    manufacturer_conflicts = ChoiceVar(
        choices=(
            (MANUFACTURER_SKIP, "Skip the merge"),
            (MANUFACTURER_CLEAR, "Clear the survivor's manufacturer"),
        ),
        label="Manufacturer conflicts",
        description="What to do when moving devices would fail the platform/manufacturer check.",
        default=MANUFACTURER_SKIP,
    )
    delete_merged_platforms = BooleanVar(
        label="Delete merged platforms",
        description=(
            "Delete a Platform once it has been emptied. Refused while it still has software "
            "versions or assigned objects, which would CASCADE."
        ),
        default=False,
    )
    update_dynamic_group_filters = BooleanVar(
        label="Update dynamic group filters",
        description="Rewrite Platform names inside DynamicGroup filters when renaming.",
        default=False,
    )
    repair_manufacturers = BooleanVar(
        label="Repair manufacturers",
        description=(
            "Rename Manufacturers the old resolution named after the device OS, such as panos to "
            "Palo Alto. Renames in place when the vendor name is free; merges when it is taken. "
            "Independent of the platform-naming mode."
        ),
        default=False,
    )
    device_type_collisions = ChoiceVar(
        choices=(
            (DEVICE_TYPE_REFUSE, "Refuse the merge"),
            (DEVICE_TYPE_MERGE, "Merge the device types"),
        ),
        label="Device type collisions",
        description="What to do when the same device type model exists under both Manufacturers.",
        default=DEVICE_TYPE_REFUSE,
    )

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta data for the consolidation job."""

        name = "LibreNMS Platform Consolidation"
        description = "Repair network drivers, rename legacy platforms, and merge duplicates."
        has_sensitive_variables = False

    def run(self, *args, **kwargs):  # pylint: disable=arguments-differ
        """Plan and optionally apply Platform consolidation."""
        # Plain BooleanVar, not DryRunVar: that forces default=False and Meta.dryrun_default only
        # sets the form initial, so an API or scheduled run omitting the field would destroy data.
        dry_run = kwargs.get("dry_run", True)
        consolidator = PlatformConsolidator(
            logger=self.logger,
            dry_run=dry_run,
            scope=kwargs.get("scope", SCOPE_LIBRENMS),
            platforms=kwargs.get("platforms"),
            repair_network_drivers=kwargs.get("repair_network_drivers", True),
            rename_legacy_platforms=kwargs.get("rename_legacy_platforms", False),
            merge_duplicates=kwargs.get("merge_duplicates", False),
            software_version_collisions=kwargs.get("software_version_collisions", COLLISION_REFUSE),
            manufacturer_conflicts=kwargs.get("manufacturer_conflicts", MANUFACTURER_SKIP),
            delete_merged_platforms=kwargs.get("delete_merged_platforms", False),
            update_dynamic_group_filters=kwargs.get("update_dynamic_group_filters", False),
            repair_manufacturers=kwargs.get("repair_manufacturers", False),
            device_type_collisions=kwargs.get("device_type_collisions", DEVICE_TYPE_REFUSE),
        )
        started = timezone.now()
        consolidator.run()

        # Reuse SSoT's own diff view and history rather than inventing a report format.
        # `render_diff` walks a plain nested dict, so a Sync record gives the operator the same
        # paginated diff UI the sync jobs produce -- without this job pretending to be a
        # two-system DataSource, which would also put it on the SSoT dashboard.
        self._record_sync(consolidator, dry_run=dry_run, started=started)

        # Nautobot renders job log messages as markdown, so the plan is also a table inline.
        # The CSVs stay attached for estates too large to read on screen.
        self.logger.info(f"**Platform plan**\n\n{consolidator.as_markdown()}")
        self.create_file("librenms_platform_consolidation.csv", consolidator.as_csv())
        if consolidator.manufacturer_plans:
            self.logger.info(f"**Manufacturer plan**\n\n{consolidator.as_manufacturer_markdown()}")
            self.create_file("librenms_manufacturer_consolidation.csv", consolidator.as_manufacturer_csv())
        if dry_run:
            self.logger.info("Dry run complete. Nothing was written.")

    def _record_sync(self, consolidator, dry_run: bool, started):
        """Store the plan as a Sync record so it appears in SSoT Sync History with a diff view."""
        sync = Sync.objects.create(
            source="Nautobot",
            target="Nautobot",
            start_time=started,
            dry_run=dry_run,
            diff=consolidator.as_diff(),
            summary=consolidator.diff_summary(),
            job_result=self.job_result,
        )
        self.logger.info(f"Recorded the plan as a Data Sync you can view as a diff: {sync.get_absolute_url()}")
        return sync


jobs = [LibrenmsDataSource, LibrenmsDataTarget, LibrenmsPlatformConsolidation]
register_jobs(*jobs)
