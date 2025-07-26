"""Jobs for OpenShift SSoT integration."""
from django.forms import ModelChoiceField
from django.templatetags.static import static
from django.urls import reverse
from nautobot.extras.jobs import BooleanVar, ObjectVar
from nautobot_ssot.jobs.base import DataMapping, DataSource

from nautobot_ssot.integrations.openshift.diffsync.adapters.adapter_nautobot import OpenshiftNautobotAdapter
from nautobot_ssot.integrations.openshift.diffsync.adapters.adapter_openshift import OpenshiftAdapter
from nautobot_ssot.integrations.openshift.models import SSOTOpenshiftConfig


name = "SSoT - OpenShift"  # pylint: disable=invalid-name


class OpenshiftDataSource(DataSource):
    """Job to sync data from OpenShift to Nautobot."""
    
    openshift_instance = ObjectVar(
        model=SSOTOpenshiftConfig,
        required=True,
        display_field="name",
        label="OpenShift Instance",
        description="The OpenShift configuration instance to sync from",
    )
    
    debug = BooleanVar(
        description="Enable for more verbose debug logging",
        default=False,
        required=False,
    )
    
    class Meta:
        """Metadata for the job."""
        name = "OpenShift ⟹ Nautobot"
        data_source = "OpenShift"
        data_source_icon = static("nautobot_ssot_openshift/openshift_logo.png")
        description = "Sync data from OpenShift to Nautobot (including KubeVirt VMs)"
        field_order = ["openshift_instance", "debug"]
    
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
        config = self.kwargs["openshift_instance"]
        self.source_adapter = OpenshiftAdapter(
            job=self,
            sync=self.sync,
            config=config,
        )
        
        # Check KubeVirt availability
        if self.source_adapter.client.kubevirt_available:
            self.job.logger.info("KubeVirt detected - will sync virtual machines")
        else:
            self.job.logger.info("KubeVirt not detected - will sync containers only")
        
        self.source_adapter.load()
    
    def load_target_adapter(self):
        """Load the Nautobot adapter."""
        self.target_adapter = OpenshiftNautobotAdapter(
            job=self,
            sync=self.sync,
        )
        self.target_adapter.load()
