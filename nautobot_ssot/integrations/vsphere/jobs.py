#  pylint: disable=keyword-arg-before-vararg
#  pylint: disable=too-few-public-methods
#  pylint: disable=too-many-locals
#  pylint: disable=abstract-method

"""Job for vSphere integration with SSoT app."""

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

from nautobot_ssot.integrations.vsphere.diffsync.adapters import (
    NBAdapter,
    VsphereDiffSync,
)
from nautobot_ssot.integrations.vsphere.models import SSOTvSphereConfig
from nautobot_ssot.integrations.vsphere.utilities import VsphereClient, VsphereConfig
from nautobot_ssot.jobs.base import DataMapping, DataSource

name = "SSoT - Virtualization"  # pylint: disable=invalid-name


def _get_vsphere_client_config(app_config, debug):
    """Get Infoblox client config from the Infoblox config instance."""
    username = app_config.vsphere_instance.secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
    )
    password = app_config.vsphere_instance.secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
    )
    vsphere_client_config = VsphereConfig(
        vsphere_uri=app_config.vsphere_instance.remote_url,
        username=username,
        password=password,
        verify_ssl=app_config.vsphere_instance.verify_ssl,
        vm_status_map=app_config.default_vm_status_map,
        ip_status_map=app_config.default_ip_status_map,
        vm_interface_map=app_config.default_vm_interface_map,
        primary_ip_sort_by=app_config.primary_ip_sort_by,
        ignore_link_local=app_config.default_ignore_link_local,
        use_clusters=app_config.use_clusters,
        sync_tagged_only=app_config.sync_tagged_only,
        debug=debug,
    )

    return vsphere_client_config


# pylint:disable=too-few-public-methods
class VsphereDataSource(DataSource):  # pylint: disable=too-many-instance-attributes
    """vSphere SSoT Data Source."""

    debug = BooleanVar(description="Enable for more verbose debug logging")
    config = ObjectVar(
        model=SSOTvSphereConfig,
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
        """Initialize vSphereDataSource."""
        super().__init__()
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE

    class Meta:
        """Metadata about this Job."""

        name = "VMWare vSphere ⟹ Nautobot"
        data_source = "VMWare vSphere"
        data_source_icon = static("nautobot_ssot_vsphere/vmware.png")
        description = "Sync data from VMWare vSphere into Nautobot."

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {"Instances": "Found in Extensibility -> External Integrations menu."}

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping(
                "Data Center",
                None,
                "ClusterGroup",
                reverse("virtualization:clustergroup_list"),
            ),
            DataMapping("Cluster", None, "Cluster", reverse("virtualization:cluster_list")),
            DataMapping(
                "Virtual Machine",
                None,
                "Virtual Machine",
                reverse("virtualization:virtualmachine_list"),
            ),
            DataMapping(
                "VM Interface",
                None,
                "VMInterface",
                reverse("virtualization:vminterface_list"),
            ),
            DataMapping("IP Addresses", None, "IP Addresses", reverse("ipam:ipaddress_list")),
        )

    def log_debug(self, message):
        """Conditionally log a debug message."""
        if self.debug:
            self.logger.debug(message)

    def load_source_adapter(self):
        """Load vSphere adapter."""
        self.logger.info("Connecting to vSphere.")
        client_config = _get_vsphere_client_config(self.config, self.debug)
        client = VsphereClient(client_config)  # pylint: disable=unexpected-keyword-arg
        if not client.is_authenticated:
            self.logger.debug("Failed to authenticate with vSphere. Check your credentials and configuration.")
            raise ValueError("vSphere authentication failed.")
        self.source_adapter = VsphereDiffSync(
            job=self,
            sync=self.sync,
            client=client,
            config=self.config,
            cluster_filters=self.cluster_filters,
        )
        self.logger.debug("Loading data from vSphere...")
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load Nautobot Adapter."""
        self.logger.info("Connecting to Nautobot...")
        self.target_adapter = NBAdapter(
            job=self,
            sync=self.sync,
            config=self.config,
            cluster_filters=self.cluster_filters,
        )

        self.logger.info("Loading current data from Nautobot...")
        self.target_adapter.load()

    def run(
        self,
        dryrun,
        memory_profiling,
        debug,
        cluster_filters,
        *args,
        **kwargs,
    ):  # pylint: disable=arguments-differ, too-many-arguments
        """Run sync."""
        self.dryrun = dryrun
        self.debug = debug
        self.memory_profiling = memory_profiling
        self.cluster_filters = cluster_filters
        self.config = kwargs.get("config")
        if not self.config.enable_sync_to_nautobot:
            self.logger.error("Can't run sync to Nautobot, provided config does not have it enabled.")
            raise ValueError("Config not enabled for sync to Nautobot.")
        options = f"`Debug`: {self.debug}, `Dry Run`: {self.dryrun}, `Sync Tagged Only`: {self.config.sync_tagged_only}, `Cluster Filter`: {self.cluster_filters}"  # NOQA
        self.logger.info(f"Starting job with the following options: {options}")
        return super().run(dryrun, memory_profiling, *args, **kwargs)


jobs = [VsphereDataSource]
