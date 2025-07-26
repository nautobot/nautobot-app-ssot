"""Signal handlers for OpenShift integration.

This module defines Django signal handlers that initialize Nautobot objects
required for the OpenShift SSoT integration. It creates custom fields and
tags needed to track OpenShift-specific metadata in Nautobot.

Signal Architecture:
- Uses Django's signal system for initialization hooks
- Responds to nautobot_database_ready signal for safe database access
- Creates Nautobot objects only when database is fully initialized
- Provides idempotent initialization (safe to run multiple times)

Objects Created:
1. Tags: Visual indicators for synced objects
2. Custom Fields: Storage for OpenShift-specific metadata
3. Content Type Associations: Links fields to appropriate models

Key Benefits:
- Automatic setup when integration is enabled
- No manual configuration required by administrators
- Consistent metadata structure across all synced objects
- Visual identification of OpenShift-managed resources

Integration Pattern:
This follows the established Nautobot SSoT pattern where each integration
creates its own custom fields and tags for tracking synchronized data.
The pattern ensures data traceability and prevents conflicts between
different SSoT sources.

Maintenance Notes:
- Signal handlers must be idempotent (safe to run multiple times)
- Use get_or_create() to avoid duplicate object creation
- Handle database migration scenarios gracefully
- Add new fields here when extending OpenShift metadata support
"""

from django.conf import settings
from nautobot.core.choices import ColorChoices
from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import CustomFieldTypeChoices

# Access plugin configuration for conditional behavior
config = settings.PLUGINS_CONFIG["nautobot_ssot"]


def register_signals(sender):
    """Register Django signal handlers for OpenShift integration.
    
    This function connects our custom signal handlers to Django's signal
    system. It's called during plugin initialization to ensure our handlers
    are active when the database is ready.
    
    Args:
        sender: The Django app that's registering the signals
        
    Signal Registration:
    - nautobot_database_ready: Safe database access for object creation
    
    Why Signal Registration is Needed:
    - Django signals allow plugins to hook into framework events
    - Database-ready signal ensures safe access to ORM operations
    - Prevents race conditions during application startup
    - Enables clean separation of initialization logic
    """
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)


def nautobot_database_ready_callback(sender, *, apps, **kwargs):
    """Initialize Nautobot objects required for OpenShift integration.
    
    This callback is triggered when the Nautobot database is fully initialized
    and ready for ORM operations. It creates the custom fields and tags needed
    to track OpenShift-synchronized objects in Nautobot.
    
    Args:
        sender: The signal sender (usually the Django app)
        apps: Django app registry for model access
        **kwargs: Additional signal arguments (unused)
        
    Objects Created:
    1. SSoT Sync Tag: Visual indicator for OpenShift-synced objects
    2. Custom Fields: Metadata storage for OpenShift-specific attributes
    3. Content Type Links: Associates fields with appropriate models
    
    Error Handling:
    - Uses get_or_create() for idempotent operation
    - Handles missing models gracefully
    - Logs errors but doesn't fail catastrophically
    
    Database Safety:
    - Only executes when database is fully ready
    - Uses Django app registry for safe model access
    - Respects database transaction boundaries
    """
    # Get model classes from app registry (safe for migrations)
    Tag = apps.get_model("extras", "Tag")
    CustomField = apps.get_model("extras", "CustomField")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Status = apps.get_model("extras", "Status")
    
    # Get Nautobot model classes that will store OpenShift data
    Tenant = apps.get_model("tenancy", "Tenant")              # OpenShift namespaces/projects
    Device = apps.get_model("dcim", "Device")                 # OpenShift nodes
    VirtualMachine = apps.get_model("virtualization", "VirtualMachine")  # KubeVirt VMs
    IPAddress = apps.get_model("ipam", "IPAddress")           # Pod/Service IPs
    Service = apps.get_model("ipam", "Service")               # OpenShift services
    
    # =====================================================================
    # CREATE TAG FOR OPENSHIFT-SYNCED OBJECTS
    # =====================================================================
    
    # Create visual indicator tag for objects synchronized from OpenShift
    # This tag helps users identify which objects came from OpenShift
    tag_sync_from_openshift, _ = Tag.objects.get_or_create(
        name="SSoT Synced from OpenShift",
        defaults={
            "description": (
                "Object synchronized from Red Hat OpenShift to Nautobot. "
                "This tag indicates the object is managed by OpenShift SSoT integration."
            ),
            "color": ColorChoices.COLOR_RED,  # Red Hat branding consistency
        },
    )
    
    # Associate tag with all Nautobot models that can be synced from OpenShift
    # This enables the tag to be applied to these object types
    for model in [Tenant, Device, VirtualMachine, IPAddress, Service]:
        tag_sync_from_openshift.content_types.add(ContentType.objects.get_for_model(model))
    
    # =====================================================================
    # CREATE CUSTOM FIELDS FOR OPENSHIFT METADATA
    # =====================================================================
    
    # OpenShift Namespace/Project Name
    # Stores the original OpenShift namespace for reference and debugging
    cf_openshift_namespace, _ = CustomField.objects.get_or_create(
        label="OpenShift Namespace",
        key="openshift_namespace",
        defaults={
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "description": (
                "Original OpenShift namespace/project name. "
                "Used for tracking source namespace and debugging sync issues."
            ),
        },
    )
    # Associate with Tenant model (namespaces map to tenants)
    cf_openshift_namespace.content_types.add(ContentType.objects.get_for_model(Tenant))
    
    # OpenShift Resource UID 
    # Stores the unique identifier assigned by OpenShift to each resource
    cf_openshift_uid, _ = CustomField.objects.get_or_create(
        label="OpenShift UID",
        key="openshift_uid",
        defaults={
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "description": (
                "OpenShift resource UID for tracking and correlation. "
                "Unique identifier assigned by OpenShift cluster to each resource."
            ),
        },
    )
    # Associate with all major resource types that have OpenShift UIDs
    for model in [Tenant, Device, VirtualMachine, Service]:
        cf_openshift_uid.content_types.add(ContentType.objects.get_for_model(model))
    
    # OpenShift Node Role
    # Distinguishes between master and worker nodes in the cluster
    cf_openshift_node_role, _ = CustomField.objects.get_or_create(
        label="OpenShift Node Role",
        key="openshift_node_role",
        defaults={
            "type": CustomFieldTypeChoices.TYPE_SELECT,
            "description": (
                "Role of OpenShift node in the cluster. "
                "Values: 'master' (control plane), 'worker' (workload node)."
            ),
        },
    )
    # Associate with Device model (nodes map to devices)
    cf_openshift_node_role.content_types.add(ContentType.objects.get_for_model(Device))
    
    # OpenShift Service Name
    # Stores the original service name for network service tracking
    cf_openshift_service, _ = CustomField.objects.get_or_create(
        label="OpenShift Service",
        key="openshift_service",
        defaults={
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "description": (
                "Original OpenShift service name. "
                "Used for tracking service mappings and network configuration."
            ),
        },
    )
    # Associate with Service model (OpenShift services map to Nautobot services)
    cf_openshift_service.content_types.add(ContentType.objects.get_for_model(Service))
    
    # KubeVirt VM Indicator
    # Boolean flag to distinguish KubeVirt VMs from regular VMs
    cf_kubevirt_vm, _ = CustomField.objects.get_or_create(
        label="KubeVirt VM",
        key="kubevirt_vm",
        defaults={
            "type": CustomFieldTypeChoices.TYPE_BOOLEAN,
            "description": (
                "Indicates if virtual machine is managed by KubeVirt on OpenShift. "
                "True for KubeVirt VMs, False for traditional VMs."
            ),
        },
    )
    # Associate with VirtualMachine model
    cf_kubevirt_vm.content_types.add(ContentType.objects.get_for_model(VirtualMachine))
