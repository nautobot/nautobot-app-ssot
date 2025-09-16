# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Network to Code, LLC
# Copyright (c) 2025 NVIDIA Corporation

"""Jobs for OpenShift SSoT integration.

This module defines the Nautobot SSoT job for synchronizing data from OpenShift
clusters to Nautobot. The job follows the established patterns for SSoT integrations
and provides secure credential handling via SecretsGroup.

Key Components:
1. OpenshiftDataSource - Main sync job class inheriting from DataSource
2. _get_openshift_client_config - Credential extraction helper function
3. Data mappings - Define how OpenShift resources map to Nautobot models

Security Architecture:
- Credentials extracted securely from SecretsGroup at runtime
- No credentials stored in job configuration or logs
- API tokens accessed via Nautobot's secrets management system

Sync Architecture:
- Uses DiffSync pattern with source (OpenShift) and target (Nautobot) adapters
- Supports both container workloads and KubeVirt virtual machines
- Continues on failure to maximize data synchronization

Error Handling:
- CONTINUE_ON_FAILURE flag prevents single failures from stopping entire sync
- KubeVirt availability checked gracefully with fallback to containers-only mode
- Comprehensive logging for troubleshooting and audit trails
"""
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


# Job group name displayed in Nautobot UI
name = "SSoT - OpenShift"  # pylint: disable=invalid-name


def _get_openshift_client_config(app_config, debug):
    """Extract OpenShift client configuration from secure storage.
    
    This function securely extracts credentials from Nautobot's SecretsGroup
    system and builds the configuration needed by the OpenShift client. It
    follows the security pattern established by other SSoT integrations.
    
    Credential Handling:
    - API token stored as either username or password in SecretsGroup
    - Falls back to username if password is empty (flexibility for different setups)
    - URL and SSL settings from ExternalIntegration
    - Sync configuration from SSOTOpenshiftConfig model
    
    Args:
        app_config (SSOTOpenshiftConfig): Configuration model instance
        debug (bool): Whether to enable debug logging
        
    Returns:
        dict: Configuration dictionary for OpenShift client containing:
            - url: OpenShift API endpoint URL
            - api_token: Service account token for authentication
            - verify_ssl: Whether to verify SSL certificates
            - sync_*: Boolean flags for each resource type
            - namespace_filter: Regex filter for namespaces
            - workload_types: Type of workloads to sync
            - debug: Debug logging flag
            
    Security Notes:
    - Credentials are only accessed when needed (just-in-time)
    - No credentials are logged or stored in the returned config
    - SecretsGroup access is audited by Nautobot
    """
    # Extract credentials from secrets group using Nautobot's secure API
    # This pattern ensures credentials are never stored in plain text
    username = app_config.openshift_instance.secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
    )
    password = app_config.openshift_instance.secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
    )
    
    # OpenShift authentication flexibility:
    # - Some setups store token as password
    # - Others store token as username (especially service accounts)
    # - Prefer password, fall back to username for maximum compatibility
    api_token = password or username
    
    # Build comprehensive client configuration
    # Combines ExternalIntegration settings with sync preferences
    openshift_config = {
        # Connection settings from ExternalIntegration
        "url": app_config.openshift_instance.remote_url,
        "api_token": api_token,
        "verify_ssl": app_config.openshift_instance.verify_ssl,
        
        # Sync control flags from SSOTOpenshiftConfig
        "sync_namespaces": app_config.sync_namespaces,
        "sync_nodes": app_config.sync_nodes,
        "sync_containers": app_config.sync_containers,
        "sync_deployments": app_config.sync_deployments,
        "sync_services": app_config.sync_services,
        "sync_kubevirt_vms": app_config.sync_kubevirt_vms,
        
        # Filtering and workload type configuration
        "namespace_filter": app_config.namespace_filter,
        "workload_types": app_config.workload_types,
        
        # Runtime options
        "debug": debug,
    }
    
    return openshift_config


class OpenshiftDataSource(DataSource):
    """OpenShift to Nautobot data synchronization job.
    
    This job implements the SSoT pattern for synchronizing OpenShift cluster
    resources to Nautobot. It supports both traditional container workloads
    and KubeVirt virtual machines, with flexible configuration options.
    
    Inheritance Hierarchy:
    DataSource -> BaseDataSource -> Job (Nautobot core)
    
    Key Features:
    1. Secure credential handling via SecretsGroup
    2. Granular control over what resources to sync
    3. Support for container and VM workloads  
    4. Namespace filtering with regex patterns
    5. Graceful error handling with CONTINUE_ON_FAILURE
    6. KubeVirt auto-detection with fallback
    
    Job Execution Flow:
    1. User selects configuration and options in UI
    2. Job validates configuration and extracts credentials
    3. Source adapter connects to OpenShift and loads data
    4. Target adapter loads existing Nautobot data
    5. DiffSync engine calculates differences
    6. Changes are applied to Nautobot with audit logging
    
    Error Handling Strategy:
    - Individual resource failures don't stop the entire sync
    - Missing KubeVirt gracefully falls back to containers-only
    - Comprehensive logging for troubleshooting
    - Validation errors clearly communicated to user
    """
    
    # =====================================================================
    # JOB PARAMETER DEFINITIONS
    # =====================================================================
    
    debug = BooleanVar(
        description=(
            "Enable verbose debug logging for troubleshooting. "
            "Warning: Debug logs may contain sensitive information. "
            "Only enable when necessary and review logs carefully."
        ),
        default=False,
        required=False,
    )
    
    config = ObjectVar(
        model=SSOTOpenshiftConfig,
        required=True,
        # Security filter: Only show enabled configurations
        # This prevents accidental execution of disabled configs
        query_params={"enable_sync_to_nautobot": True, "job_enabled": True},
        label="OpenShift Configuration",
        description=(
            "Select the OpenShift configuration to sync from. "
            "Only configurations that are enabled for sync jobs will appear. "
            "The selected config determines what resources are synchronized."
        ),
    )
    
    def __init__(self):
        """Initialize the OpenShift data source job.
        
        Sets up DiffSync behavior to continue processing even if individual
        resources fail. This maximizes the amount of data synchronized in
        case of partial API failures or data inconsistencies.
        """
        super().__init__()
        # Continue processing even if individual items fail
        # This ensures maximum data synchronization in case of partial failures
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE
    
    class Meta:
        """Job metadata configuration.
        
        Defines how the job appears in the Nautobot UI and its behavior.
        The data_source_icon should match the integration's visual identity.
        """
        name = "OpenShift ⟹ Nautobot"  # Unicode arrow for visual clarity
        data_source = "OpenShift"
        data_source_icon = static("nautobot_ssot_openshift/openshift_logo.png")
        description = (
            "Synchronize data from Red Hat OpenShift to Nautobot. "
            "Supports container workloads, KubeVirt virtual machines, "
            "nodes, services, and namespaces."
        )
        field_order = ["config", "debug"]  # UI field display order
    
    @classmethod
    def data_mappings(cls):
        """Define mapping between OpenShift and Nautobot resources.
        
        This method tells the SSoT framework and UI what OpenShift resources
        map to which Nautobot models. Used for documentation and user
        understanding of what the sync will accomplish.
        
        Returns:
            tuple: DataMapping objects describing each resource type mapping
            
        Mapping Logic:
        - OpenShift Projects/Namespaces → Nautobot Tenants (organizational structure)
        - OpenShift Nodes → Nautobot Devices (physical/virtual infrastructure)
        - Container Pods → Nautobot Applications (container workloads)
        - Deployments → Nautobot Applications (application definitions)
        - KubeVirt VMs → Nautobot Virtual Machines (virtualized workloads)
        - OpenShift Services → Nautobot Services (network services)
        """
        return (
            # Projects provide organizational hierarchy
            DataMapping(
                "Project/Namespace", 
                None,  # No source URL - OpenShift doesn't expose web UI URLs via API
                "Tenant", 
                reverse("tenancy:tenant_list")
            ),
            
            # Nodes are the underlying infrastructure
            DataMapping(
                "Node", 
                None, 
                "Device", 
                reverse("dcim:device_list")
            ),
            
            # Container workloads as applications
            DataMapping(
                "Container/Pod", 
                None, 
                "Application", 
                reverse("extras:application_list")
            ),
            
            # Higher-level application definitions
            DataMapping(
                "Deployment", 
                None, 
                "Application", 
                reverse("extras:application_list")
            ),
            
            # KubeVirt virtual machines (if available)
            DataMapping(
                "KubeVirt VM", 
                None, 
                "Virtual Machine", 
                reverse("virtualization:virtualmachine_list")
            ),
            
            # Network services and endpoints
            DataMapping(
                "Service", 
                None, 
                "Service", 
                reverse("ipam:service_list")
            ),
        )
    
    def load_source_adapter(self):
        """Initialize and load the OpenShift source adapter.
        
        This method is called by the SSoT framework to set up the source
        side of the synchronization. It handles credential extraction,
        client initialization, and data loading from OpenShift.
        
        Process Flow:
        1. Extract configuration from job parameters
        2. Build secure client configuration (credentials from SecretsGroup)
        3. Initialize OpenShift adapter with client config
        4. Check for KubeVirt availability and log status
        5. Load all configured resources from OpenShift
        
        Error Handling:
        - Invalid configurations will raise ValidationError
        - Network/API errors will raise connection exceptions
        - Missing KubeVirt is handled gracefully (not an error)
        """
        # Get configuration selected by user in job form
        config = self.kwargs["config"]
        
        # Extract credentials securely and build client configuration
        # This is where SecretsGroup credentials are accessed
        client_config = _get_openshift_client_config(
            config, 
            self.kwargs.get("debug", False)
        )
        
        # Initialize OpenShift adapter with secure configuration
        # Adapter will handle API connection and resource discovery
        self.source_adapter = OpenshiftAdapter(
            job=self,                    # Reference for logging and status updates
            sync=self.sync,              # DiffSync engine instance
            config=config,               # Model configuration object
            client_config=client_config, # Runtime configuration with credentials
        )
        
        # Check for KubeVirt support and inform user
        # KubeVirt is optional - absence is not an error condition
        if hasattr(self.source_adapter, 'client') and self.source_adapter.client.kubevirt_available:
            self.logger.info(
                "KubeVirt detected on OpenShift cluster - will sync virtual machines"
            )
        else:
            self.logger.info(
                "KubeVirt not detected - will sync container workloads only"
            )
        
        # Load all configured resources from OpenShift
        # This populates the source adapter's DiffSync store
        self.source_adapter.load()
    
    def load_target_adapter(self):
        """Initialize and load the Nautobot target adapter.
        
        This method sets up the target side of the synchronization by
        loading existing Nautobot data that corresponds to OpenShift
        resources. The adapter will create missing Nautobot objects
        and update existing ones as needed.
        
        Process Flow:
        1. Initialize Nautobot adapter with job context
        2. Load existing Nautobot objects that might correspond to OpenShift resources
        3. Prepare for receiving sync updates from OpenShift data
        
        Note: Target adapter doesn't need explicit configuration since
        it operates on the local Nautobot database using Django ORM.
        """
        # Initialize Nautobot adapter
        # No external credentials needed - uses local database
        self.target_adapter = OpenshiftNautobotAdapter(
            job=self,        # Reference for logging and status updates
            sync=self.sync,  # DiffSync engine instance for coordination
        )
        
        # Load existing Nautobot data that might correspond to OpenShift resources
        # This includes tenants, devices, VMs, applications, and services
        # that were previously synced or manually created
        self.target_adapter.load()
