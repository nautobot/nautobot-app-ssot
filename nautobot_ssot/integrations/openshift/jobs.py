"""Jobs for OpenShift SSoT integration."""
from diffsync.enum import DiffSyncFlags
from django.templatetags.static import static
from django.urls import reverse
from nautobot.extras.choices import (
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)
from nautobot.extras.jobs import BooleanVar, ObjectVar
from nautobot_ssot.jobs.base import DataMapping, DataSource

from nautobot_ssot.integrations.openshift.diffsync.adapters.adapter_nautobot import OpenshiftNautobotAdapter
from nautobot_ssot.integrations.openshift.diffsync.adapters.adapter_openshift import OpenshiftAdapter
from nautobot_ssot.integrations.openshift.models import SSOTOpenshiftConfig


name = "SSoT - OpenShift"  # pylint: disable=invalid-name


def _get_openshift_client_config(app_config, debug):
    """Get OpenShift client config from the config instance."""
    # Extract credentials from secrets group
    username = app_config.openshift_instance.secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
    )
    password = app_config.openshift_instance.secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
    )
    
    # For OpenShift, username is typically "openshift" and password is the API token
    api_token = password or username  # Fallback to username if password is empty
    
    openshift_config = {
        "url": app_config.openshift_instance.remote_url,
        "api_token": api_token,
        "verify_ssl": app_config.openshift_instance.verify_ssl,
        "sync_namespaces": app_config.sync_namespaces,
        "sync_nodes": app_config.sync_nodes,
        "sync_containers": app_config.sync_containers,
        "sync_deployments": app_config.sync_deployments,
        "sync_services": app_config.sync_services,
        "sync_kubevirt_vms": app_config.sync_kubevirt_vms,
        "namespace_filter": app_config.namespace_filter,
        "workload_types": app_config.workload_types,
        "debug": debug,
    }
    
    return openshift_config


class OpenshiftDataSource(DataSource):
    """Job to sync data from OpenShift to Nautobot."""
    
    debug = BooleanVar(
        description="Enable for more verbose debug logging",
        default=False,
        required=False,
    )
    
    config = ObjectVar(
        model=SSOTOpenshiftConfig,
        required=True,
        query_params={"enable_sync_to_nautobot": True, "job_enabled": True},
        label="OpenShift Configuration",
        description="The OpenShift configuration instance to sync from",
    )
    
    def __init__(self):
        """Initialize OpenShiftDataSource."""
        super().__init__()
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE
    
    class Meta:
        """Metadata for the job."""
        name = "OpenShift ⟹ Nautobot"
        data_source = "OpenShift"
        data_source_icon = static("nautobot_ssot_openshift/openshift_logo.png")
        description = "Sync data from OpenShift to Nautobot (including KubeVirt VMs)"
        field_order = ["config", "debug"]
    
    @classmethod
    def data_mappings(cls):
        """Define the data mappings for this job."""
        return (
            DataMapping("Project/Namespace", None, "Tenant", reverse("tenancy:tenant_list")),
            DataMapping("Node", None, "Device", reverse("dcim:device_list")),
            DataMapping("Container/Pod", None, "Application", reverse("extras:application_list")),
            DataMapping("Deployment", None, "Application", reverse("extras:application_list")),
            DataMapping("KubeVirt VM", None, "Virtual Machine", reverse("virtualization:virtualmachine_list")),
            DataMapping("Service", None, "Service", reverse("ipam:service_list")),
        )
    
    def load_source_adapter(self):
        """Load the OpenShift adapter."""
        config = self.kwargs["config"]
        client_config = _get_openshift_client_config(config, self.kwargs.get("debug", False))
        
        self.source_adapter = OpenshiftAdapter(
            job=self,
            sync=self.sync,
            config=config,
            client_config=client_config,
        )
        
        # Check KubeVirt availability
        if hasattr(self.source_adapter, 'client') and self.source_adapter.client.kubevirt_available:
            self.logger.info("KubeVirt detected - will sync virtual machines")
        else:
            self.logger.info("KubeVirt not detected - will sync containers only")
        
        self.source_adapter.load()
    
    def load_target_adapter(self):
        """Load the Nautobot adapter."""
        self.target_adapter = OpenshiftNautobotAdapter(
            job=self,
            sync=self.sync,
        )
        self.target_adapter.load()
