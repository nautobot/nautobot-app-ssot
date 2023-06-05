"""Jobs for Infoblox integration with SSoT plugin."""

from django.templatetags.static import static
from django.urls import reverse
from nautobot.extras.jobs import BooleanVar, Job
from nautobot_ssot.jobs.base import DataMapping, DataSource, DataTarget

from diffsync import DiffSyncFlags
from nautobot_ssot_infoblox.diffsync.adapters import infoblox, nautobot
from nautobot_ssot_infoblox.utils.client import InfobloxApi
from nautobot_ssot_infoblox.constant import PLUGIN_CFG


name = "SSoT - Infoblox DDI"  # pylint: disable=invalid-name


class InfobloxDataSource(DataSource, Job):
    """Infoblox SSoT Data Source."""

    debug = BooleanVar(description="Enable for verbose debug logging.")

    def __init__(self):
        """Initialize InfobloxDataSource."""
        super().__init__()
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE | DiffSyncFlags.SKIP_UNMATCHED_DST

    class Meta:  # pylint: disable=too-few-public-methods
        """Information about the Job."""

        name = "Infoblox ⟹ Nautobot"
        data_source = "Infoblox"
        data_source_icon = static("nautobot_ssot_infoblox/infoblox_logo.png")
        description = "Sync infomation from Infoblox to Nautobot"

    @classmethod
    def data_mappings(cls):
        """Show mapping of models between Infoblox and Nautobot."""
        return (
            DataMapping("network", None, "Prefix", reverse("ipam:prefix_list")),
            DataMapping("ipaddress", None, "IP Address", reverse("ipam:ipaddress_list")),
            DataMapping("vlan", None, "VLAN", reverse("ipam:vlan_list")),
            DataMapping("vlanview", None, "VLANGroup", reverse("ipam:vlangroup_list")),
        )

    def load_source_adapter(self):
        """Load Infoblox data."""
        self.log_info(message="Connecting to Infoblox")
        client = InfobloxApi()
        self.source_adapter = infoblox.InfobloxAdapter(job=self, sync=self.sync, conn=client)
        self.log_info(message="Loading data from Infoblox...")
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load Nautobot data."""
        self.log_info(message="Connecting to Nautobot...")
        self.target_adapter = nautobot.NautobotAdapter(job=self, sync=self.sync)
        self.log_info(message="Loading data from Nautobot...")
        self.target_adapter.load()


class InfobloxDataTarget(DataTarget, Job):
    """Infoblox SSoT Data Target."""

    debug = BooleanVar(description="Enable for verbose debug logging.")

    def __init__(self):
        """Initialize InfobloxDataTarget."""
        super().__init__()
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE | DiffSyncFlags.SKIP_UNMATCHED_DST

    class Meta:  # pylint: disable=too-few-public-methods
        """Information about the Job."""

        name = "Nautobot ⟹ Infoblox"
        data_target = "Infoblox"
        data_target_icon = static("nautobot_ssot_infoblox/infoblox_logo.png")
        description = "Sync infomation from Nautobot to Infoblox"

    @classmethod
    def data_mappings(cls):
        """Show mapping of models between Nautobot and Infoblox."""
        return (
            DataMapping("Prefix", reverse("ipam:prefix_list"), "network", None),
            DataMapping("IP Address", reverse("ipam:ipaddress_list"), "ipaddress", None),
            DataMapping("VLAN", reverse("ipam:vlan_list"), "vlan", None),
            DataMapping("VLANGroup", reverse("ipam:vlangroup_list"), "vlanview", None),
        )

    def load_source_adapter(self):
        """Load Nautobot data."""
        self.log_info(message="Connecting to Nautobot...")
        self.source_adapter = nautobot.NautobotAdapter(job=self, sync=self.sync)
        self.log_info(message="Loading data from Nautobot...")
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load Infoblox data."""
        self.log_info(message="Connecting to Infoblox")
        client = InfobloxApi()
        self.target_adapter = infoblox.InfobloxAdapter(job=self, sync=self.sync, conn=client)
        self.log_info(message="Loading data from Infoblox...")
        self.target_adapter.load()


class InfobloxNetworkContainerSource(DataSource, Job):
    """Infoblox SSoT Network Container Source."""

    debug = BooleanVar(description="Enable for verbose debug logging.")

    def __init__(self):
        """Initialize InfobloxNetworkContainerSource."""
        super().__init__()
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE

    class Meta:  # pylint: disable=too-few-public-methods
        """Information about the Job."""

        name = "Infoblox ⟹ Nautobot -  Network Containers"
        data_source = "InfobloxNetworkContainers"
        data_source_icon = static("nautobot_ssot_infoblox/infoblox_logo.png")
        description = "Sync Network Container (Aggregate) infomation from Infoblox to Nautobot"

    @classmethod
    def data_mappings(cls):
        """Show mapping of models between Infoblox and Nautobot."""
        return (DataMapping("networkcontainer", None, "Aggregate", reverse("ipam:aggregate_list")),)

    def load_source_adapter(self):
        """Load Infoblox data."""
        self.log_info(message="Connecting to Infoblox")
        client = InfobloxApi()
        self.source_adapter = infoblox.InfobloxAggregateAdapter(job=self, sync=self.sync, conn=client)
        self.log_info(message="Loading data from Infoblox...")
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load Nautobot data."""
        self.log_info(message="Connecting to Nautobot...")
        self.target_adapter = nautobot.NautobotAggregateAdapter(job=self, sync=self.sync)
        self.log_info(message="Loading data from Nautobot...")
        self.target_adapter.load()


jobs = [InfobloxDataSource]

if PLUGIN_CFG["enable_sync_to_infoblox"]:
    jobs.append(InfobloxDataTarget)

if PLUGIN_CFG["enable_rfc1918_network_containers"]:
    jobs.append(InfobloxNetworkContainerSource)
