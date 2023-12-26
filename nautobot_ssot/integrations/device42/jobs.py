# pylint: disable=too-few-public-methods
"""Jobs for Device42 integration with SSoT app."""

from django.templatetags.static import static
from django.urls import reverse
from nautobot.extras.jobs import BooleanVar
from nautobot_ssot.jobs.base import DataMapping, DataSource

from nautobot_ssot.integrations.device42.constant import PLUGIN_CFG
from nautobot_ssot.integrations.device42.diffsync.adapters.device42 import Device42Adapter
from nautobot_ssot.integrations.device42.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.integrations.device42.utils.device42 import Device42API


name = "SSoT - Device42"  # pylint: disable=invalid-name


class Device42DataSource(DataSource):  # pylint: disable=too-many-instance-attributes
    """Device42 SSoT Data Source."""

    debug = BooleanVar(description="Enable for more verbose debug logging", default=False)
    bulk_import = BooleanVar(description="Enable using bulk create option for object creation.", default=False)

    class Meta:
        """Meta data for Device42."""

        name = "Device42"
        data_source = "Device42"
        data_source_icon = static("nautobot_ssot_device42/d42_logo.png")
        description = "Sync information from Device42 to Nautobot"

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {
            "Device42 Host": PLUGIN_CFG.get("device42_host"),
            "Username": PLUGIN_CFG.get("device42_username"),
            "Verify SSL": str(PLUGIN_CFG.get("device42_verify_ssl")),
        }

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping(
                "Buildings", f"{PLUGIN_CFG['device42_host']}admin/rackraj/building/", "Sites", reverse("dcim:site_list")
            ),
            DataMapping(
                "Rooms",
                f"{PLUGIN_CFG['device42_host']}admin/rackraj/room/",
                "Rack Groups",
                reverse("dcim:rackgroup_list"),
            ),
            DataMapping(
                "Racks", f"{PLUGIN_CFG['device42_host']}admin/rackraj/rack/", "Racks", reverse("dcim:rack_list")
            ),
            DataMapping(
                "Vendors",
                f"{PLUGIN_CFG['device42_host']}admin/rackraj/organisation/",
                "Manufacturers",
                reverse("dcim:manufacturer_list"),
            ),
            DataMapping(
                "Hardware Models",
                f"{PLUGIN_CFG['device42_host']}admin/rackraj/hardware/",
                "Device Types",
                reverse("dcim:devicetype_list"),
            ),
            DataMapping(
                "Devices", f"{PLUGIN_CFG['device42_host']}admin/rackraj/device/", "Devices", reverse("dcim:device_list")
            ),
            DataMapping(
                "Ports",
                f"{PLUGIN_CFG['device42_host']}admin/rackraj/netport/",
                "Interfaces",
                reverse("dcim:interface_list"),
            ),
            DataMapping(
                "Cables", f"{PLUGIN_CFG['device42_host']}admin/rackraj/cable/", "Cables", reverse("dcim:cable_list")
            ),
            DataMapping(
                "VPC (VRF Groups)",
                f"{PLUGIN_CFG['device42_host']}admin/rackraj/vrfgroup/",
                "VRFs",
                reverse("ipam:vrf_list"),
            ),
            DataMapping(
                "Subnets", f"{PLUGIN_CFG['device42_host']}admin/rackraj/vlan/", "Prefixes", reverse("ipam:prefix_list")
            ),
            DataMapping(
                "IP Addresses",
                f"{PLUGIN_CFG['device42_host']}admin/rackraj/ip_address/",
                "IP Addresses",
                reverse("ipam:ipaddress_list"),
            ),
            DataMapping(
                "VLANs", f"{PLUGIN_CFG['device42_host']}admin/rackraj/switch_vlan/", "VLANs", reverse("ipam:vlan_list")
            ),
            DataMapping(
                "Vendors",
                f"{PLUGIN_CFG['device42_host']}admin/rackraj/organisation/",
                "Providers",
                reverse("circuits:provider_list"),
            ),
            DataMapping(
                "Telco Circuits",
                f"{PLUGIN_CFG['device42_host']}admin/rackraj/circuit/",
                "Circuits",
                reverse("circuits:circuit_list"),
            ),
        )

    def load_source_adapter(self):
        """Load data from Device42 into DiffSync models."""
        if self.debug:
            self.logger.info("Connecting to Device42...")
        client = Device42API(
            base_url=PLUGIN_CFG["device42_host"],
            username=PLUGIN_CFG["device42_username"],
            password=PLUGIN_CFG["device42_password"],
            verify=PLUGIN_CFG["device42_verify_ssl"],
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
        self, dryrun, memory_profiling, debug, bulk_import, *args, **kwargs
    ):
        """Perform data synchronization."""
        self.bulk_import = bulk_import
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [Device42DataSource]
