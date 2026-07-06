#  pylint: disable=keyword-arg-before-vararg
#  pylint: disable=too-few-public-methods
#  pylint: disable=too-many-locals
#  pylint: disable=abstract-method
#  pylint: disable=duplicate-code

"""Job for the Proxmox VE integration with the SSoT app."""

from diffsync.enum import DiffSyncFlags
from django.templatetags.static import static
from django.urls import reverse
from nautobot.apps.jobs import MultiObjectVar, ObjectVar
from nautobot.extras.choices import (
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)
from nautobot.extras.jobs import BooleanVar
from nautobot.virtualization.models import Cluster

from nautobot_ssot.integrations.proxmox.diffsync.adapters import (
    NBAdapter,
    ProxmoxDiffSync,
)
from nautobot_ssot.integrations.proxmox.models import SSOTProxmoxConfig
from nautobot_ssot.integrations.proxmox.utilities import ProxmoxClient, ProxmoxConfig
from nautobot_ssot.jobs.base import DataMapping, DataSource

name = "SSoT - Virtualization"  # pylint: disable=invalid-name


def _get_proxmox_client_config(app_config, debug):
    """Build the Proxmox client config from the SSOTProxmoxConfig instance."""
    token_id = app_config.proxmox_instance.secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
    )
    token_secret = app_config.proxmox_instance.secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
    )
    proxmox_client_config = ProxmoxConfig(
        proxmox_uri=app_config.proxmox_instance.remote_url,
        token_id=token_id,
        token_secret=token_secret,
        verify_ssl=app_config.proxmox_instance.verify_ssl,
        vm_status_map=app_config.default_vm_status_map,
        ip_status_map=app_config.default_ip_status_map,
        primary_ip_sort_by=app_config.primary_ip_sort_by,
        ignore_link_local=app_config.default_ignore_link_local,
        use_clusters=app_config.use_clusters,
        sync_lxc=app_config.sync_lxc,
        sync_nodes_as_devices=app_config.sync_nodes_as_devices,
        sync_proxmox_tags=app_config.sync_proxmox_tags,
        debug=debug,
    )
    return proxmox_client_config


class ProxmoxDataSource(DataSource):  # pylint: disable=too-many-instance-attributes
    """Proxmox VE SSoT Data Source."""

    debug = BooleanVar(description="Enable for more verbose debug logging")
    config = ObjectVar(
        model=SSOTProxmoxConfig,
        required=True,
        query_params={"enable_sync_to_nautobot": True, "job_enabled": True},
    )
    cluster_filters = MultiObjectVar(
        label="Cluster Filters",
        model=Cluster,
        required=False,
        description="Only sync Virtual Machines from the selected Clusters.",
    )

    def __init__(self):
        """Initialize ProxmoxDataSource."""
        super().__init__()
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE

    class Meta:
        """Metadata about this Job."""

        name = "Proxmox VE ⟹ Nautobot"
        data_source = "Proxmox VE"
        data_source_icon = static("nautobot_ssot_proxmox/proxmox.png")
        description = "Sync data from Proxmox VE into Nautobot."

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {"Instances": "Found in Extensibility -> External Integrations menu."}

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping("Cluster", None, "ClusterGroup", reverse("virtualization:clustergroup_list")),
            DataMapping("Cluster", None, "Cluster", reverse("virtualization:cluster_list")),
            DataMapping("Node", None, "Device", reverse("dcim:device_list")),
            DataMapping("Node Interface", None, "Interface", reverse("dcim:interface_list")),
            DataMapping("Virtual Machine", None, "Virtual Machine", reverse("virtualization:virtualmachine_list")),
            DataMapping("VM Interface", None, "VMInterface", reverse("virtualization:vminterface_list")),
            DataMapping("IP Addresses", None, "IP Addresses", reverse("ipam:ipaddress_list")),
        )

    def log_debug(self, message):
        """Conditionally log a debug message."""
        if self.debug:
            self.logger.debug(message)

    def load_source_adapter(self):
        """Load the Proxmox VE adapter."""
        self.logger.info("Connecting to Proxmox VE.")
        client_config = _get_proxmox_client_config(self.config, self.debug)
        client = ProxmoxClient(client_config)
        if not client.is_authenticated:
            self.logger.error("Failed to authenticate with Proxmox VE. Check your credentials and configuration.")
            raise ValueError("Proxmox VE authentication failed.")
        self.source_adapter = ProxmoxDiffSync(
            job=self,
            sync=self.sync,
            client=client,
            config=self.config,
            cluster_filters=self.cluster_filters,
        )
        self.logger.info("Loading data from Proxmox VE...")
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load the Nautobot adapter."""
        self.logger.info("Connecting to Nautobot...")
        self.target_adapter = NBAdapter(
            job=self,
            sync=self.sync,
            config=self.config,
            cluster_filters=self.cluster_filters,
        )
        self.logger.info("Loading current data from Nautobot...")
        self.target_adapter.load()

    def run(self, *args, **kwargs):
        """Run the sync."""
        self.dryrun = kwargs.get("dryrun")
        self.debug = kwargs.get("debug")
        self.cluster_filters = kwargs.get("cluster_filters")
        self.config = kwargs.get("config")
        if not self.config.enable_sync_to_nautobot:
            self.logger.error("Can't run sync to Nautobot, provided config does not have it enabled.")
            raise ValueError("Config not enabled for sync to Nautobot.")
        options = (
            f"`Debug`: {self.debug}, `Dry Run`: {self.dryrun}, `Sync LXC`: {self.config.sync_lxc}, "
            f"`Sync Nodes as Devices`: {self.config.sync_nodes_as_devices}, "
            f"`Cluster Filter`: {','.join([cluster.name for cluster in self.cluster_filters])}"
        )
        self.logger.info(f"Starting job with the following options: {options}")
        super().run(*args, **kwargs)


jobs = [ProxmoxDataSource]
