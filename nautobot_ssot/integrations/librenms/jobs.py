"""Jobs for LibreNMS SSoT integration."""

import os

from django.templatetags.static import static
from nautobot.apps.jobs import BooleanVar, ChoiceVar, ObjectVar
from nautobot.core.celery import register_jobs
from nautobot.dcim.models import LocationType
from nautobot.extras.choices import (
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)
from nautobot.extras.models import ExternalIntegration
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.librenms.diffsync.adapters import librenms, nautobot
from nautobot_ssot.integrations.librenms.utils.librenms import LibreNMSApi
from nautobot_ssot.jobs.base import DataMapping, DataSource, DataTarget

name = "LibreNMS SSoT"  # pylint: disable=invalid-name


class LibrenmsDataSource(DataSource):
    """LibreNMS SSoT Data Source."""

    librenms_server = ObjectVar(
        model=ExternalIntegration,
        queryset=ExternalIntegration.objects.all(),
        display_field="display",
        required=True,
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
    load_type = ChoiceVar(
        choices=(
            ("file", "file"),
            ("api", "api"),
        ),
        description="Load LibreNMS from local fixutres or External Integration API.",
        label="Data Load Source",
        default="api",
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

    def run(
        self,
        dryrun,
        memory_profiling,
        debug,
        librenms_server,
        hostname_field,
        sync_locations,
        location_type,
        tenant,
        load_type,
        *args,
        **kwargs,
    ):  # pylint: disable=arguments-differ
        """Perform data synchronization."""
        self.librenms_server = librenms_server
        self.hostname_field = hostname_field
        self.load_type = load_type
        self.sync_locations = sync_locations
        self.location_type = location_type
        self.tenant = tenant
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


class LibrenmsDataTarget(DataTarget):
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
        self.source_adapter = nautobot.NautobotAdapter(job=self, sync=self.sync)
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

    def run(
        self,
        dryrun,
        memory_profiling,
        debug,
        librenms_server,
        force_add,
        ping_fallback,
        sync_locations,
        location_type,
        tenant,
        *args,
        **kwargs,
    ):  # pylint: disable=arguments-differ
        """Perform data synchronization."""
        self.librenms_server = librenms_server
        self.force_add = force_add
        self.ping_fallback = ping_fallback
        self.sync_locations = sync_locations
        self.location_type = location_type
        self.hostname_field = "env_var"
        self.load_type = "api"
        self.tenant = tenant
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [LibrenmsDataSource, LibrenmsDataTarget]
register_jobs(*jobs)
