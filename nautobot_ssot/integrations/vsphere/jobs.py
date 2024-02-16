#  pylint: disable=keyword-arg-before-vararg
#  pylint: disable=too-few-public-methods
#  pylint: disable=too-many-locals
#  pylint: disable=abstract-method

"""Job for vSphere integration with SSoT app."""

from diffsync.enum import DiffSyncFlags
from django.templatetags.static import static
from django.urls import reverse
from nautobot.apps.jobs import ObjectVar
from nautobot.core.forms import DynamicModelChoiceField
from nautobot.extras.choices import (
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)
from nautobot.extras.jobs import BooleanVar
from nautobot.virtualization.models import Cluster

from nautobot_ssot.integrations.vsphere.diffsync.adapters import (
    Adapter,
    VsphereDiffSync,
)
from nautobot_ssot.integrations.vsphere.models import SSOTvSphereConfig
from nautobot_ssot.integrations.vsphere.utilities import VsphereClient
from nautobot_ssot.jobs.base import DataMapping, DataSource

name = "SSoT - Virtualization"  # pylint: disable=invalid-name


# class OptionalObjectVar(ScriptVariable):
#     """Custom implementation of an Optional ObjectVar.

#     An object primary key is returned and accessible in job kwargs.
#     """

#     form_field = DynamicModelChoiceField

#     def __init__(
#         self,
#         model=None,
#         display_field="display",
#         query_params=None,
#         null_option=None,
#         *args,
#         **kwargs,
#     ):
#         """Init."""
#         super().__init__(*args, **kwargs)

#         if model is not None:
#             self.field_attrs["queryset"] = model.objects.all()
#         else:
#             raise TypeError("ObjectVar must specify a model")

#         self.field_attrs.update(
#             {
#                 "display_field": display_field,
#                 "query_params": query_params,
#                 "null_option": null_option,
#             }
#         )


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
    vsphere_client_config = {
        "vsphere_uri": app_config.vsphere_instance.remote_url,
        "username": username,
        "password": password,
        "verify_ssl": app_config.vsphere_instance.verify_ssl,
        "default_vm_status_map": app_config.default_vm_status_map,
        "default_ip_status_map": app_config.default_ip_status_map,
        "default_vm_interface_map": app_config.default_vm_interface_map,
        "primary_ip_sort_by": app_config.primary_ip_sort_by,
        "ignore_link_local": app_config.default_ignore_link_local,
        "debug": debug,
    }

    return vsphere_client_config


# pylint:disable=too-few-public-methods
class VsphereDataSource(DataSource):  # pylint: disable=too-many-instance-attributes
    """vSphere SSoT Data Source."""

    debug = BooleanVar(description="Enable for more verbose debug logging")
    config = ObjectVar(
        model=SSOTvSphereConfig,
        display_field="SSOT vSphere Config",
        required=True,
        query_params={"enable_sync_to_nautobot": True, "job_enabled": True},
    )
    sync_vsphere_tagged_only = BooleanVar(
        default=False,
        label="Sync Tagged Only",
        description="Only sync objects that have the 'ssot-synced-from-vsphere' tag.",
    )
    cluster_filter = DynamicModelChoiceField(
        label="Only sync Nautobot records belonging to a single Cluster.",
        queryset=Cluster.objects.all(),
        required=False,
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
        client = VsphereClient(  # pylint: disable=unexpected-keyword-arg
            **client_config
        )
        self.source_adapter = VsphereDiffSync(
            job=self,
            sync=self.sync,
            client=client,
            config=self.config,
            cluster_filter=self.cluster_filter_object,
        )
        self.logger.debug("Loading data from vSphere...")
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load Nautobot Adapter."""
        self.logger.info("Connecting to Nautobot...")
        self.target_adapter = Adapter(
            job=self,
            sync=self.sync,
            config=self.config,
            sync_vsphere_tagged_only=self.sync_vsphere_tagged_only,
            cluster_filter=self.cluster_filter_object,
        )

        self.logger.info(message="Loading current data from Nautobot...")
        self.target_adapter.load()

    def run(
        self,
        dryrun,
        memory_profiling,
        debug,
        sync_vsphere_tagged_only,
        cluster_filter=None,
        *args,
        **kwargs,
    ):  # pylint: disable=arguments-differ, too-many-arguments
        """Run sync."""
        self.dryrun = dryrun
        self.debug = debug
        self.memory_profiling = memory_profiling
        self.sync_vsphere_tagged_only = sync_vsphere_tagged_only
        self.cluster_filter = cluster_filter
        self.cluster_filter_object = (  # pylint: disable=attribute-defined-outside-init
            Cluster.objects.get(pk=self.cluster_filter) if self.cluster_filter else None
        )
        self.config = kwargs.get("config")
        if not self.config.enable_sync_to_nautobot:
            self.logger.error("Can't run sync to Nautobot, provided config does not have it enabled.")
            raise ValueError("Config not enabled for sync to Nautobot.")
        options = f"`Debug`: {self.debug}, `Dry Run`: {self.dryrun}, `Sync Tagged Only`: {self.sync_vsphere_tagged_only}, `Cluster Filter`: {self.cluster_filter_object}"  # NOQA
        self.logger.info(message=f"Starting job with the following options: {options}")
        return super().run(dryrun, memory_profiling, sync_vsphere_tagged_only, *args, **kwargs)


jobs = [VsphereDataSource]
