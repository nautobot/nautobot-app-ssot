"""Jobs for the Cisco SD-WAN SSoT integration."""

from diffsync.enum import DiffSyncFlags
from django.conf import settings
from django.urls import reverse
from nautobot.apps.jobs import BooleanVar, MultiObjectVar, ObjectVar, StringVar, register_jobs
from nautobot.dcim.models import Controller, ControllerManagedDeviceGroup, Device, Location, Platform
from nautobot.extras.models import Role, SecretsGroup, Status
from nautobot.tenancy.models import Tenant

from nautobot_ssot.exceptions import JobException
from nautobot_ssot.integrations.cisco_sdwan.constants import DATA_SOURCE_NAME
from nautobot_ssot.integrations.cisco_sdwan.diffsync.adapters.cisco_sdwan import CiscoSdwanRemoteAdapter
from nautobot_ssot.integrations.cisco_sdwan.diffsync.adapters.nautobot import CiscoSdwanNautobotAdapter
from nautobot_ssot.jobs.base import DataMapping, DataSource

name = "Cisco SD-WAN SSoT"  # pylint: disable=invalid-name


class CiscoSdwanDataSource(DataSource):  # pylint: disable=too-many-instance-attributes
    """Cisco SD-WAN SSoT Data Source."""

    debug = BooleanVar(description="Enable for more verbose debug logging", default=False)
    controller = ObjectVar(
        model=Controller,
        queryset=Controller.objects.all(),
        description="Cisco Catalyst SD-WAN Manager.",
        display_field="display",
        label="Catalyst SD-WAN Manager",
        required=True,
    )
    managed_device_group = ObjectVar(
        model=ControllerManagedDeviceGroup,
        queryset=ControllerManagedDeviceGroup.objects.all(),
        query_params={"controller": "$controller"},
        description="Managed device group associated with the controller.",
        display_field="display",
        label="Controller Managed Device Group",
        required=True,
    )
    devices = MultiObjectVar(
        model=Device,
        query_params={"role": "$device_role"},
        description="Sync data only for the specified devices.",
        display_field="display",
        label="Devices",
        required=False,
    )
    device_status = ObjectVar(
        model=Status,
        query_params={"content_types": "dcim.device"},
        description="Status assigned to imported Devices.",
        display_field="display",
        label="Device Status",
        required=True,
    )
    device_role = ObjectVar(
        model=Role,
        query_params={"content_types": "dcim.device"},
        description="Role assigned to imported Devices.",
        display_field="display",
        label="Device Role",
        required=True,
    )
    device_platform = ObjectVar(
        model=Platform,
        description="Platform assigned to imported Devices.",
        display_field="display",
        label="Device Platform",
        required=True,
    )
    device_location = ObjectVar(
        model=Location,
        description="Staging Location assigned to newly imported Devices. Existing Device locations are never updated.",
        display_field="display",
        label="Device Location",
        required=True,
    )
    device_secrets_group = ObjectVar(
        model=SecretsGroup,
        description="Secrets Group assigned to imported Devices.",
        display_field="display",
        label="Secrets Group",
        required=True,
    )
    device_tenant = ObjectVar(
        model=Tenant,
        description="Tenant assigned to imported Devices.",
        display_field="display",
        label="Tenant",
        required=False,
    )
    model_normalization = StringVar(
        label="Device Model Normalization",
        description="Regex pattern to be removed from the SD-WAN Device Model.",
        default="^vedge-",
        required=False,
    )
    ignore_address_mask = BooleanVar(
        description="Ignore identical IP addresses with different subnet masks.", default=True
    )
    delete_replaced_ips = BooleanVar(
        label="Delete Replaced IP Addresses",
        description=(
            "Delete IPAddress objects that are replaced on an interface and no longer assigned anywhere. "
            "When disabled, replaced addresses are only unassigned."
        ),
        default=False,
    )

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta data for Cisco SD-WAN."""

        name = "Cisco SD-WAN to Nautobot"
        data_source = DATA_SOURCE_NAME
        data_target = "Nautobot"
        description = "Sync information from Cisco SD-WAN to Nautobot"
        has_sensitive_variables = False
        field_order = [
            "dryrun",
            "debug",
            "controller",
            "managed_device_group",
            "devices",
            "device_status",
            "device_role",
            "device_platform",
            "device_location",
            "device_secrets_group",
            "device_tenant",
            "model_normalization",
            "ignore_address_mask",
            "delete_replaced_ips",
        ]

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {}

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping("Device Models", None, "DeviceTypes", reverse("dcim:devicetype_list")),
            DataMapping("Software Versions", None, "SoftwareVersions", reverse("dcim:softwareversion_list")),
            DataMapping("Devices", None, "Devices", reverse("dcim:device_list")),
            DataMapping("Interfaces", None, "Interfaces", reverse("dcim:interface_list")),
            DataMapping("Interface IPv4 Addresses", None, "IP Addresses", reverse("ipam:ipaddress_list")),
            DataMapping("VPNs", None, "VRFs", reverse("ipam:vrf_list")),
        )

    def __init__(self):
        """Initialize CiscoSdwanDataSource."""
        super().__init__()
        self.diffsync_flags = (
            self.diffsync_flags | DiffSyncFlags.CONTINUE_ON_FAILURE
        ) & ~DiffSyncFlags.LOG_UNCHANGED_RECORDS

    def validate_metadata_configuration(self):
        """Ensure the SSoT metadata feature is enabled for this Job.

        The Nautobot adapter scopes shared objects (DeviceTypes, SoftwareVersions) to those
        previously synchronized by this integration using the object metadata that the SSoT
        framework records when `enable_metadata_for` includes this Job class.
        """
        metadata_jobs = settings.PLUGINS_CONFIG.get("nautobot_ssot", {}).get("enable_metadata_for", [])
        if self.__class__.__name__ not in metadata_jobs:
            self.logger.error(
                "The Cisco SD-WAN integration requires the SSoT metadata feature. Add "
                '`"enable_metadata_for": ["CiscoSdwanDataSource"]` to the `nautobot_ssot` '
                "settings in your `PLUGINS_CONFIG` and re-run the Job."
            )
            raise JobException(message="Metadata is not enabled for the CiscoSdwanDataSource Job.")

    def load_source_adapter(self):
        """Load data from Cisco SD-WAN into DiffSync models."""
        self.source_adapter = CiscoSdwanRemoteAdapter(job=self, sync=self.sync)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.target_adapter = CiscoSdwanNautobotAdapter(job=self, sync=self.sync)
        self.target_adapter.load()

    def run(
        self,
        dryrun,
        memory_profiling,
        debug,
        controller,
        managed_device_group,
        device_status,
        devices,
        device_role,
        device_platform,
        device_location,
        device_secrets_group,
        device_tenant,
        model_normalization,
        ignore_address_mask,
        delete_replaced_ips,
        *args,
        **kwargs,
    ):  # pylint: disable=arguments-differ, too-many-arguments, too-many-locals
        """Perform data synchronization."""
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        self.controller = controller
        self.managed_device_group = managed_device_group
        self.device_status = device_status
        self.devices = devices
        self.device_role = device_role
        self.device_platform = device_platform
        self.device_location = device_location
        self.device_secrets_group = device_secrets_group
        self.device_tenant = device_tenant
        self.model_normalization = model_normalization
        self.ignore_address_mask = ignore_address_mask
        self.delete_replaced_ips = delete_replaced_ips
        self.validate_metadata_configuration()
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [CiscoSdwanDataSource]
register_jobs(*jobs)
