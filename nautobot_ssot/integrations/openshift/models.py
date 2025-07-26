"""Models for Red Hat OpenShift integration."""
from django.core.exceptions import ValidationError
from django.db import models
from nautobot.core.models.generics import PrimaryModel

from nautobot_ssot.integrations.utils import get_json_type_choices


class SSOTOpenshiftConfig(PrimaryModel):
    """Model for storing OpenShift integration configuration."""
    
    is_saved_view_model = False
    
    name = models.CharField(max_length=200, unique=True)
    description = models.CharField(max_length=200, blank=True)
    url = models.URLField(
        max_length=200,
        verbose_name="OpenShift API URL",
        help_text="The URL of the OpenShift API server (e.g., https://api.cluster.example.com:6443)"
    )
    api_token = models.CharField(
        max_length=500,
        verbose_name="API Token",
        help_text="Service account token for authentication"
    )
    verify_ssl = models.BooleanField(
        default=True,
        verbose_name="Verify SSL",
        help_text="Verify SSL certificates when connecting to OpenShift"
    )
    
    # Sync options
    sync_namespaces = models.BooleanField(
        default=True,
        verbose_name="Sync Namespaces/Projects",
        help_text="Import OpenShift projects as Nautobot tenants"
    )
    sync_nodes = models.BooleanField(
        default=True,
        verbose_name="Sync Nodes",
        help_text="Import OpenShift nodes as Nautobot devices"
    )
    sync_containers = models.BooleanField(
        default=True,
        verbose_name="Sync Containers",
        help_text="Import container workloads as Nautobot applications"
    )
    sync_deployments = models.BooleanField(
        default=True,
        verbose_name="Sync Deployments",
        help_text="Import OpenShift deployments as Nautobot applications"
    )
    sync_services = models.BooleanField(
        default=True,
        verbose_name="Sync Services",
        help_text="Import OpenShift services as Nautobot services"
    )
    sync_kubevirt_vms = models.BooleanField(
        default=True,
        verbose_name="Sync KubeVirt VMs",
        help_text="Import KubeVirt virtual machines as Nautobot VMs (requires KubeVirt)"
    )
    
    # Filtering options
    namespace_filter = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Namespace Filter",
        help_text="Regex pattern to filter namespaces (leave empty to sync all)"
    )
    
    # Workload type options
    workload_types = models.CharField(
        max_length=50,
        choices=[
            ("all", "All Workloads"),
            ("containers", "Containers Only"),
            ("vms", "Virtual Machines Only"),
        ],
        default="all",
        verbose_name="Workload Types",
        help_text="Types of workloads to synchronize"
    )
    
    class Meta:
        """Metaclass for SSOTOpenshiftConfig."""
        ordering = ["name"]
        verbose_name = "SSoT OpenShift Configuration"
        verbose_name_plural = "SSoT OpenShift Configurations"

    def __str__(self):
        """String representation."""
        return self.name

    def clean(self):
        """Validate the configuration."""
        super().clean()
        
        if not self.url.startswith(("https://", "http://")):
            raise ValidationError({"url": "URL must start with http:// or https://"})
        
        if not self.api_token:
            raise ValidationError({"api_token": "API token is required"})
        
        # At least one sync option must be enabled
        sync_options = [
            self.sync_namespaces, self.sync_nodes, self.sync_containers,
            self.sync_deployments, self.sync_services, self.sync_kubevirt_vms
        ]
        if not any(sync_options):
            raise ValidationError("At least one sync option must be enabled")
        
        # Validate workload type selection
        if self.workload_types == "vms" and not self.sync_kubevirt_vms:
            raise ValidationError({
                "workload_types": "Cannot select 'VMs Only' when KubeVirt VM sync is disabled"
            })

    def get_absolute_url(self):
        """Return the absolute URL for this object."""
        return f"/plugins/nautobot-ssot/openshift/config/{self.pk}/"
