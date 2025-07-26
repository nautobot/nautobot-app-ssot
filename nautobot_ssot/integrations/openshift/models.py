"""Models for Red Hat OpenShift integration.

This module defines the Django models used to store configuration for the OpenShift
Single Source of Truth integration. The main model SSOTOpenshiftConfig stores all
the necessary configuration to connect to an OpenShift cluster and synchronize
various workload types (containers, VMs, services, etc.) to Nautobot.

Architecture Notes:
- Uses ExternalIntegration for secure credential management via SecretsGroup
- Follows Nautobot SSoT patterns established by vSphere integration
- Supports both container workloads and KubeVirt virtual machines
- Provides granular control over what resources to sync

Security Model:
- Credentials (API tokens) stored in Nautobot's SecretsGroup system
- No plain-text credential storage in this model
- Access controlled through ExternalIntegration permissions
"""
from django.core.exceptions import ValidationError
from django.db import models

# Import field length constants for consistency with Nautobot standards
try:
    from nautobot.apps.constants import CHARFIELD_MAX_LENGTH
except ImportError:
    # Fallback for older Nautobot versions
    CHARFIELD_MAX_LENGTH = 255

from nautobot.core.models.generics import PrimaryModel
from nautobot.extras.choices import (
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)
from nautobot.extras.models import SecretsGroupAssociation


class SSOTOpenshiftConfig(PrimaryModel):
    """Configuration model for OpenShift SSoT integration.
    
    This model stores all configuration needed to connect to an OpenShift cluster
    and synchronize various workload types to Nautobot. It follows the established
    pattern of using ExternalIntegration for secure credential management.
    
    Key Design Decisions:
    1. Uses ExternalIntegration instead of direct credential fields for security
    2. Provides boolean flags for each sync type (namespaces, nodes, containers, etc.)
    3. Supports filtering by namespace patterns for selective synchronization
    4. Includes job control flags to enable/disable configurations
    5. Validates that at least one sync option is enabled
    
    Relationship Patterns:
    - openshift_instance (ForeignKey): Links to ExternalIntegration for credentials
    - No direct credential storage - all handled through SecretsGroup
    
    Usage Example:
        config = SSOTOpenshiftConfig.objects.create(
            name="Production OpenShift",
            openshift_instance=external_integration,
            sync_namespaces=True,
            sync_kubevirt_vms=True,
            workload_types="all"
        )
    """
    
    # Basic identification fields
    name = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH, 
        unique=True,
        help_text="Unique name for this OpenShift configuration"
    )
    description = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH, 
        blank=True,
        help_text="Optional description of this configuration's purpose"
    )
    
    # Security: External integration handles credentials securely
    openshift_instance = models.ForeignKey(
        to="extras.ExternalIntegration",
        on_delete=models.PROTECT,  # Prevent deletion if configs exist
        verbose_name="OpenShift Instance Config",
        help_text=(
            "External Integration containing OpenShift API URL, credentials, "
            "and SSL verification settings. Credentials are stored securely "
            "in a SecretsGroup and accessed at runtime."
        ),
    )
    
    # =====================================================================
    # SYNC OPTION FIELDS - Control what resources to synchronize
    # =====================================================================
    # These boolean fields provide granular control over which OpenShift 
    # resources are synchronized to Nautobot. Each maps to a specific
    # Nautobot model type and sync adapter logic.
    
    sync_namespaces = models.BooleanField(
        default=True,
        verbose_name="Sync Namespaces/Projects",
        help_text=(
            "Import OpenShift projects/namespaces as Nautobot tenants. "
            "Provides organizational structure for other resources."
        )
    )
    
    sync_nodes = models.BooleanField(
        default=True,
        verbose_name="Sync Nodes",
        help_text=(
            "Import OpenShift worker and master nodes as Nautobot devices. "
            "Includes node capacity, status, and role information."
        )
    )
    
    sync_containers = models.BooleanField(
        default=True,
        verbose_name="Sync Containers",
        help_text=(
            "Import container workloads (Pods) as Nautobot applications. "
            "Excludes KubeVirt VM pods which are handled separately."
        )
    )
    
    sync_deployments = models.BooleanField(
        default=True,
        verbose_name="Sync Deployments",
        help_text=(
            "Import OpenShift deployments as Nautobot applications. "
            "Provides higher-level application grouping beyond individual pods."
        )
    )
    
    sync_services = models.BooleanField(
        default=True,
        verbose_name="Sync Services",
        help_text=(
            "Import OpenShift services as Nautobot services. "
            "Maps service endpoints and load balancer configurations."
        )
    )
    
    sync_kubevirt_vms = models.BooleanField(
        default=True,
        verbose_name="Sync KubeVirt VMs",
        help_text=(
            "Import KubeVirt virtual machines as Nautobot VMs. "
            "Requires KubeVirt to be installed on the OpenShift cluster. "
            "VMs are detected by special pod labels and handled differently."
        )
    )
    
    # =====================================================================
    # FILTERING AND WORKLOAD TYPE OPTIONS
    # =====================================================================
    
    namespace_filter = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH,
        blank=True,
        verbose_name="Namespace Filter",
        help_text=(
            "Regex pattern to filter which namespaces to sync. "
            "Examples: '^prod-.*' (production only), '^(dev|test)-.*' (dev and test). "
            "Leave empty to sync all namespaces."
        )
    )
    
    workload_types = models.CharField(
        max_length=50,
        choices=[
            ("all", "All Workloads"),           # Sync both containers and VMs
            ("containers", "Containers Only"),   # Only container workloads  
            ("vms", "Virtual Machines Only"),    # Only KubeVirt VMs
        ],
        default="all",
        verbose_name="Workload Types",
        help_text=(
            "Limit synchronization to specific workload types. "
            "'All' syncs everything enabled above. "
            "'Containers Only' excludes VMs even if KubeVirt sync is enabled. "
            "'VMs Only' syncs only KubeVirt VMs (requires sync_kubevirt_vms=True)."
        )
    )
    
    # =====================================================================
    # JOB CONTROL FLAGS - Following vSphere integration patterns
    # =====================================================================
    
    job_enabled = models.BooleanField(
        default=False,  # Conservative default - must be explicitly enabled
        verbose_name="Job Enabled",
        help_text=(
            "Enable this configuration for sync jobs. "
            "Jobs will only show configurations where this is True. "
            "Provides safety mechanism to prevent accidental syncs."
        ),
    )
    
    enable_sync_to_nautobot = models.BooleanField(
        default=True,
        verbose_name="Enable Sync to Nautobot",
        help_text=(
            "Enable synchronization from OpenShift to Nautobot. "
            "Future versions may support bidirectional sync - this flag "
            "controls the OpenShift->Nautobot direction."
        ),
    )
    
    class Meta:
        """Django model metadata configuration."""
        ordering = ["name"]  # Default ordering for admin and API
        verbose_name = "SSoT OpenShift Configuration"
        verbose_name_plural = "SSoT OpenShift Configurations"

    def __str__(self):
        """Return human-readable string representation.
        
        Used in Django admin, API responses, and form dropdowns.
        Simple name-based representation for easy identification.
        """
        return self.name

    def clean(self):
        """Validate model data before saving.
        
        This method implements business logic validation that goes beyond
        simple field validation. Called automatically by Django's validation
        system and explicitly by validated_save().
        
        Validation Rules:
        1. At least one sync option must be enabled (prevents empty configs)
        2. workload_types="vms" requires sync_kubevirt_vms=True (logical consistency)
        
        Raises:
            ValidationError: If validation rules are violated
        """
        super().clean()  # Call parent validation first
        
        # Rule 1: Ensure at least one resource type is enabled for sync
        # This prevents configurations that would do nothing when executed
        sync_options = [
            self.sync_namespaces, 
            self.sync_nodes, 
            self.sync_containers,
            self.sync_deployments, 
            self.sync_services, 
            self.sync_kubevirt_vms
        ]
        
        if not any(sync_options):
            raise ValidationError(
                "At least one sync option must be enabled. "
                "A configuration with no sync options would not perform any work."
            )
        
        # Rule 2: Validate workload type consistency
        # If user selects "VMs Only", they must also enable VM sync
        if self.workload_types == "vms" and not self.sync_kubevirt_vms:
            raise ValidationError({
                "workload_types": (
                    "Cannot select 'VMs Only' when KubeVirt VM sync is disabled. "
                    "Either change workload_types to 'all' or 'containers', "
                    "or enable sync_kubevirt_vms."
                )
            })

    def get_absolute_url(self):
        """Return the canonical URL for this configuration.
        
        Used by Django admin and other UI components to generate links
        to this object's detail page. Follows Nautobot URL patterns.
        
        Returns:
            str: URL path for this configuration's detail view
        """
        return f"/plugins/nautobot-ssot/openshift/config/{self.pk}/"
    
    # =====================================================================
    # UTILITY METHODS FOR MAINTENANCE AND DEBUGGING
    # =====================================================================
    
    def get_enabled_sync_options(self):
        """Return list of enabled sync option names.
        
        Utility method for debugging and logging to easily see what
        will be synchronized with this configuration.
        
        Returns:
            list: Names of enabled sync options (e.g., ['namespaces', 'nodes'])
        """
        enabled = []
        if self.sync_namespaces:
            enabled.append('namespaces')
        if self.sync_nodes:
            enabled.append('nodes')
        if self.sync_containers:
            enabled.append('containers')
        if self.sync_deployments:
            enabled.append('deployments')
        if self.sync_services:
            enabled.append('services')
        if self.sync_kubevirt_vms:
            enabled.append('kubevirt_vms')
        return enabled
    
    def is_ready_for_sync(self):
        """Check if configuration is ready for synchronization.
        
        Validates that all required components are properly configured
        for a sync job to execute successfully.
        
        Returns:
            bool: True if ready for sync, False otherwise
        """
        # Check basic enablement flags
        if not self.job_enabled or not self.enable_sync_to_nautobot:
            return False
            
        # Check that ExternalIntegration exists and has secrets
        if not self.openshift_instance:
            return False
            
        if not self.openshift_instance.secrets_group:
            return False
            
        # Check that at least one sync option is enabled
        return len(self.get_enabled_sync_options()) > 0
