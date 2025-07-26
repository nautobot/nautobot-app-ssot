"""Signal handlers for OpenShift integration."""

from django.conf import settings
from nautobot.core.choices import ColorChoices
from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import CustomFieldTypeChoices

config = settings.PLUGINS_CONFIG["nautobot_ssot"]


def register_signals(sender):
    """Register signals for the OpenShift integration."""
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)


def nautobot_database_ready_callback(sender, *, apps, **kwargs):
    """Create CustomFields and Tags for OpenShift integration."""
    Tag = apps.get_model("extras", "Tag")
    CustomField = apps.get_model("extras", "CustomField")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Status = apps.get_model("extras", "Status")
    
    # Get content types
    Tenant = apps.get_model("tenancy", "Tenant")
    Device = apps.get_model("dcim", "Device")
    VirtualMachine = apps.get_model("virtualization", "VirtualMachine")
    IPAddress = apps.get_model("ipam", "IPAddress")
    Service = apps.get_model("ipam", "Service")
    
    # Create tag for OpenShift synced objects
    tag_sync_from_openshift, _ = Tag.objects.get_or_create(
        name="SSoT Synced from OpenShift",
        defaults={
            "description": "Object synced from Red Hat OpenShift to Nautobot",
            "color": ColorChoices.COLOR_RED,
        },
    )
    
    # Add content types to tag
    for model in [Tenant, Device, VirtualMachine, IPAddress, Service]:
        tag_sync_from_openshift.content_types.add(ContentType.objects.get_for_model(model))
    
    # Create custom fields for OpenShift metadata
    cf_openshift_namespace, _ = CustomField.objects.get_or_create(
        label="OpenShift Namespace",
        key="openshift_namespace",
        defaults={
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "description": "OpenShift namespace/project name",
        },
    )
    cf_openshift_namespace.content_types.add(ContentType.objects.get_for_model(Tenant))
    
    cf_openshift_uid, _ = CustomField.objects.get_or_create(
        label="OpenShift UID",
        key="openshift_uid",
        defaults={
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "description": "OpenShift resource UID",
        },
    )
    for model in [Tenant, Device, VirtualMachine, Service]:
        cf_openshift_uid.content_types.add(ContentType.objects.get_for_model(model))
    
    cf_openshift_node_role, _ = CustomField.objects.get_or_create(
        label="OpenShift Node Role",
        key="openshift_node_role",
        defaults={
            "type": CustomFieldTypeChoices.TYPE_SELECT,
            "description": "Role of OpenShift node (master/worker)",
        },
    )
    cf_openshift_node_role.content_types.add(ContentType.objects.get_for_model(Device))
    
    cf_openshift_service, _ = CustomField.objects.get_or_create(
        label="OpenShift Service",
        key="openshift_service",
        defaults={
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "description": "OpenShift service name",
        },
    )
    cf_openshift_service.content_types.add(ContentType.objects.get_for_model(Service))
    
    cf_kubevirt_vm, _ = CustomField.objects.get_or_create(
        label="KubeVirt VM",
        key="kubevirt_vm",
        defaults={
            "type": CustomFieldTypeChoices.TYPE_BOOLEAN,
            "description": "Indicates if VM is managed by KubeVirt",
        },
    )
    cf_kubevirt_vm.content_types.add(ContentType.objects.get_for_model(VirtualMachine))
