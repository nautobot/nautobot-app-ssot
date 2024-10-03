# pylint: disable=too-few-public-methods
"""Jobs for Device42 integration with SSoT app."""

from django.templatetags.static import static
from django.urls import reverse
from nautobot.dcim.models import LocationType
from nautobot.extras.jobs import BooleanVar, ObjectVar
from nautobot.extras.models import ExternalIntegration

from nautobot_ssot.integrations.device42.diffsync.adapters.device42 import Device42Adapter
from nautobot_ssot.integrations.device42.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.integrations.device42.utils.device42 import Device42API
from nautobot_ssot.integrations.device42.utils.nautobot import ensure_contenttypes_on_location_type
from nautobot_ssot.jobs.base import DataMapping, DataSource
from nautobot_ssot.utils import get_username_password_https_from_secretsgroup

name = "SSoT - Device42"  # pylint: disable=invalid-name


class Device42DataSource(DataSource):  # pylint: disable=too-many-instance-attributes
    """Device42 SSoT Data Source."""

    debug = BooleanVar(description="Enable for more verbose debug logging", default=False)
    bulk_import = BooleanVar(
        description="Perform bulk operations when importing data. CAUTION! Might cause bad data to be pushed to Nautobot.",
        default=False,
    )
    integration = ObjectVar(
        model=ExternalIntegration,
        queryset=ExternalIntegration.objects.all(),
        display_field="name",
        required=True,
        label="Device42 Instance",
    )
    building_loctype = ObjectVar(
        model=LocationType,
        queryset=LocationType.objects.all(),
        display_field="name",
        required=False,
        label="Building LocationType",
        description="LocationType to use for imported Buildings from Device42. If unspecified, will revert to Site LocationType.",
    )

    class Meta:
        """Meta data for Device42."""

        name = "Device42"
        data_source = "Device42"
        data_source_icon = static("nautobot_ssot_device42/d42_logo.png")
        description = "Sync information from Device42 to Nautobot"

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {}

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping(
                "Buildings", "<Device42 Remote URL>/admin/rackraj/building/", "Locations", reverse("dcim:location_list")
            ),
            DataMapping(
                "Rooms",
                "<Device42 Remote URL>/admin/rackraj/room/",
                "Rack Groups",
                reverse("dcim:rackgroup_list"),
            ),
            DataMapping("Racks", "<Device42 Remote URL>/admin/rackraj/rack/", "Racks", reverse("dcim:rack_list")),
            DataMapping(
                "Vendors",
                "<Device42 Remote URL>/admin/rackraj/organisation/",
                "Manufacturers",
                reverse("dcim:manufacturer_list"),
            ),
            DataMapping(
                "Hardware Models",
                "<Device42 Remote URL>/admin/rackraj/hardware/",
                "Device Types",
                reverse("dcim:devicetype_list"),
            ),
            DataMapping(
                "Devices", "<Device42 Remote URL>/admin/rackraj/device/", "Devices", reverse("dcim:device_list")
            ),
            DataMapping(
                "Ports",
                "<Device42 Remote URL>/admin/rackraj/netport/",
                "Interfaces",
                reverse("dcim:interface_list"),
            ),
            DataMapping("Cables", "<Device42 Remote URL>/admin/rackraj/cable/", "Cables", reverse("dcim:cable_list")),
            DataMapping(
                "VPC (VRF Groups)",
                "<Device42 Remote URL>/admin/rackraj/vrfgroup/",
                "VRFs",
                reverse("ipam:vrf_list"),
            ),
            DataMapping(
                "Subnets", "<Device42 Remote URL>/admin/rackraj/vlan/", "Prefixes", reverse("ipam:prefix_list")
            ),
            DataMapping(
                "IP Addresses",
                "<Device42 Remote URL>/admin/rackraj/ip_address/",
                "IP Addresses",
                reverse("ipam:ipaddress_list"),
            ),
            DataMapping(
                "VLANs", "<Device42 Remote URL>/admin/rackraj/switch_vlan/", "VLANs", reverse("ipam:vlan_list")
            ),
            DataMapping(
                "Vendors",
                "<Device42 Remote URL>/admin/rackraj/organisation/",
                "Providers",
                reverse("circuits:provider_list"),
            ),
            DataMapping(
                "Telco Circuits",
                "<Device42 Remote URL>/admin/rackraj/circuit/",
                "Circuits",
                reverse("circuits:circuit_list"),
            ),
        )

    def load_source_adapter(self):
        """Load data from Device42 into DiffSync models."""
        if self.debug:
            self.logger.info("Connecting to Device42...")
        _sg = self.integration.secrets_group
        username, password = get_username_password_https_from_secretsgroup(group=_sg)
        client = Device42API(
            base_url=self.integration.remote_url,
            username=username,
            password=password,
            verify=self.integration.verify_ssl,
        )
        self.source_adapter = Device42Adapter(job=self, sync=self.sync, client=client)
        if self.debug:
            self.logger.info("Loading data from Device42...")
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.target_adapter = NautobotAdapter(job=self, sync=self.sync)
        if self.debug:
            self.logger.info("Loading data from Nautobot...")
        self.target_adapter.load()

    def run(  # pylint: disable=arguments-differ, too-many-arguments
        self, dryrun, memory_profiling, integration, debug, bulk_import, building_loctype, *args, **kwargs
    ):
        """Perform data synchronization."""
        self.integration = integration
        self.bulk_import = bulk_import
        self.building_loctype = building_loctype
        if not self.building_loctype:
            self.building_loctype = LocationType.objects.get_or_create(name="Site")[0]
        ensure_contenttypes_on_location_type(location_type=self.building_loctype)
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [Device42DataSource]
