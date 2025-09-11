"""Jobs for Forward Networks integration with SSoT app."""

from django.templatetags.static import static
from django.urls import reverse
from nautobot.extras.jobs import BooleanVar, StringVar

from nautobot_ssot.integrations.forward_networks.clients import ForwardNetworksClient
from nautobot_ssot.integrations.forward_networks.diffsync.adapters import ForwardNetworksAdapter, NautobotAdapter
from nautobot_ssot.jobs.base import DataMapping, DataSource, DataTarget

name = "SSoT - Forward Networks"


class ForwardNetworksDataSource(DataSource):
    """Forward Networks SSoT Data Source."""

    debug = BooleanVar(description="Enable for more verbose debug logging", default=False)
    network_id = StringVar(description="Forward Networks Network ID to sync from", required=True, label="Network ID")

    class Meta:
        """Meta data for Forward Networks."""

        name = "Forward Networks ⟹ Nautobot"
        data_source = "Forward Networks"
        data_source_icon = static("nautobot_ssot/img/forward_networks_logo.png")
        description = "Sync information from Forward Networks to Nautobot"

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {
            "Forward Networks URL": "Base URL for Forward Networks instance",
            "Username": "Username for Forward Networks API access",
            "Password": "Password for Forward Networks API access",
            "Verify SSL": "Whether to verify SSL certificates",
        }

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping(
                "Networks",
                "Forward Networks Network Objects",
                "Locations",
                reverse("dcim:location_list"),
            ),
            DataMapping(
                "Locations",
                "Forward Networks Location Objects",
                "Locations",
                reverse("dcim:location_list"),
            ),
            DataMapping(
                "Devices",
                "Forward Networks Device Objects",
                "Devices",
                reverse("dcim:device_list"),
            ),
            DataMapping(
                "Interfaces",
                "Forward Networks Interface Objects",
                "Interfaces",
                reverse("dcim:interface_list"),
            ),
            DataMapping(
                "IP Addresses",
                "Forward Networks IP Address Objects",
                "IP Addresses",
                reverse("ipam:ipaddress_list"),
            ),
            DataMapping(
                "Prefixes",
                "Forward Networks Prefix Objects",
                "Prefixes",
                reverse("ipam:prefix_list"),
            ),
            DataMapping(
                "VLANs",
                "Forward Networks VLAN Objects",
                "VLANs",
                reverse("ipam:vlan_list"),
            ),
        )

    def load_source_adapter(self):
        """Load data from Forward Networks into DiffSync models."""
        if self.debug:
            self.logger.info("Connecting to Forward Networks...")

        # Get credentials from settings or environment
        # Note: This would need to be configured properly in a real implementation
        forward_networks_url = "https://your-forward-networks-instance.com"
        username = "your-username"
        # Credentials should be configured through environment variables or secrets management
        # This is a placeholder and should not contain actual credentials
        user_password = "configure-your-password"  # noqa: S105

        client = ForwardNetworksClient(
            base_url=forward_networks_url,
            username=username,
            password=user_password,
            verify_ssl=True,
        )

        self.source_adapter = ForwardNetworksAdapter(
            job=self,
            sync=self.sync,
            client=client,
            network_id=self.network_id,
        )

        if self.debug:
            self.logger.info("Loading data from Forward Networks...")
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.target_adapter = NautobotAdapter(job=self, sync=self.sync)
        if self.debug:
            self.logger.info("Loading data from Nautobot...")
        self.target_adapter.load()

    def run(self, dryrun, memory_profiling, debug, network_id, *args, **kwargs):
        """Run the sync job."""
        self.debug = debug
        self.network_id = network_id

        super().run(dryrun=dryrun, memory_profiling=memory_profiling, *args, **kwargs)


class ForwardNetworksDataTarget(DataTarget):
    """Forward Networks SSoT Data Target."""

    debug = BooleanVar(description="Enable for more verbose debug logging", default=False)
    network_id = StringVar(description="Forward Networks Network ID to sync to", required=True, label="Network ID")

    class Meta:
        """Meta data for Forward Networks."""

        name = "Nautobot ⟹ Forward Networks"
        data_target = "Forward Networks"
        data_target_icon = static("nautobot_ssot/img/forward_networks_logo.png")
        description = "Sync information from Nautobot to Forward Networks"

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataTarget."""
        return {
            "Forward Networks URL": "Base URL for Forward Networks instance",
            "Username": "Username for Forward Networks API access",
            "Password": "Password for Forward Networks API access",
            "Verify SSL": "Whether to verify SSL certificates",
        }

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataTarget."""
        return (
            DataMapping(
                "Locations",
                reverse("dcim:location_list"),
                "Locations",
                "Forward Networks Location Objects",
            ),
            DataMapping(
                "Devices",
                reverse("dcim:device_list"),
                "Devices",
                "Forward Networks Device Objects",
            ),
            DataMapping(
                "Device Tags",
                reverse("extras:tag_list"),
                "Device Tags",
                "Forward Networks Device Tag Objects",
            ),
        )

    def load_source_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.source_adapter = NautobotAdapter(job=self, sync=self.sync)
        if self.debug:
            self.logger.info("Loading data from Nautobot...")
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Forward Networks into DiffSync models."""
        if self.debug:
            self.logger.info("Connecting to Forward Networks...")

        # Get credentials from settings or environment
        forward_networks_url = "https://your-forward-networks-instance.com"
        username = "your-username"
        # Credentials should be configured through environment variables or secrets management
        # This is a placeholder and should not contain actual credentials
        user_password = "configure-your-password"  # noqa: S105

        client = ForwardNetworksClient(
            base_url=forward_networks_url,
            username=username,
            password=user_password,
            verify_ssl=True,
        )

        self.target_adapter = ForwardNetworksAdapter(
            job=self,
            sync=self.sync,
            client=client,
            network_id=self.network_id,
        )

        if self.debug:
            self.logger.info("Loading data from Forward Networks...")
        self.target_adapter.load()

    def run(self, dryrun, memory_profiling, debug, network_id, *args, **kwargs):
        """Run the sync job."""
        self.debug = debug
        self.network_id = network_id

        super().run(dryrun=dryrun, memory_profiling=memory_profiling, *args, **kwargs)


jobs = [ForwardNetworksDataSource, ForwardNetworksDataTarget]
