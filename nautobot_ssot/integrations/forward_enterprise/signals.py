"""Signals for Forward Enterprise integration."""

from django.conf import settings
from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import CustomFieldTypeChoices

from nautobot_ssot.integrations.forward_enterprise import constants
from nautobot_ssot.utils import create_or_update_custom_field

config = settings.PLUGINS_CONFIG["nautobot_ssot"]


# pylint: disable=R0801
def register_signals(sender):
    """Register signals for Forward Enterprise integration."""
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)


def nautobot_database_ready_callback(sender, *, apps, **kwargs):  # pylint: disable=unused-argument
    """Callback function triggered by the nautobot_database_ready signal when the Nautobot database is fully ready."""
    # Get models from app registry
    # pylint: disable=invalid-name, too-many-locals
    Device = apps.get_model("dcim", "Device")
    DeviceType = apps.get_model("dcim", "DeviceType")
    InventoryItem = apps.get_model("dcim", "InventoryItem")
    Interface = apps.get_model("dcim", "Interface")
    IPAddress = apps.get_model("ipam", "IPAddress")
    Location = apps.get_model("dcim", "Location")
    VLAN = apps.get_model("ipam", "VLAN")
    VRF = apps.get_model("ipam", "VRF")
    Prefix = apps.get_model("ipam", "Prefix")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Role = apps.get_model("extras", "Role")
    Status = apps.get_model("extras", "Status")
    Tag = apps.get_model("extras", "Tag")

    # Create custom fields for system of record tracking
    sync_custom_field, _ = create_or_update_custom_field(
        apps,
        key="last_synced_from_sor",
        field_type=CustomFieldTypeChoices.TYPE_DATE,
        label="Last sync from System of Record",
    )
    sor_custom_field, _ = create_or_update_custom_field(
        apps,
        key="system_of_record",
        field_type=CustomFieldTypeChoices.TYPE_TEXT,
        label="System of Record",
    )

    # Apply custom fields to Forward Enterprise relevant models
    forward_enterprise_models = [Device, DeviceType, Interface, IPAddress, Location, VLAN, VRF, Prefix]
    for model in forward_enterprise_models:
        model_ct = ContentType.objects.get_for_model(model)
        sor_custom_field.content_types.add(model_ct.id)
        sync_custom_field.content_types.add(model_ct.id)

    # Roles
    Role.objects.get_or_create(
        name=constants.DEFAULT_DEVICE_ROLE,
        defaults={"color": constants.DEFAULT_DEVICE_ROLE_COLOR},
    )

    # Ensure the Role is set to apply to the Device model
    device_role = Role.objects.get(name=constants.DEFAULT_DEVICE_ROLE)
    device_content_type = ContentType.objects.get_for_model(Device)
    device_role.content_types.add(device_content_type)

    # Device Status
    Status.objects.get_or_create(
        name=constants.DEFAULT_DEVICE_STATUS,
        defaults={"color": constants.DEFAULT_DEVICE_STATUS_COLOR},
    )

    # Tag for SSoT Synced from Forward Enterprise
    tag_sync_from_forward, _ = Tag.objects.get_or_create(
        name="SSoT Synced from Forward Enterprise",
        defaults={
            "description": "Object synced at some point from Forward Enterprise",
            "color": constants.TAG_COLOR,
        },
    )
    tag_sync_from_forward.content_types.add(ContentType.objects.get_for_model(Device))
    tag_sync_from_forward.content_types.add(ContentType.objects.get_for_model(DeviceType))
    tag_sync_from_forward.content_types.add(ContentType.objects.get_for_model(InventoryItem))
    tag_sync_from_forward.content_types.add(ContentType.objects.get_for_model(Interface))
    tag_sync_from_forward.content_types.add(ContentType.objects.get_for_model(IPAddress))
    tag_sync_from_forward.content_types.add(ContentType.objects.get_for_model(Location))
    tag_sync_from_forward.content_types.add(ContentType.objects.get_for_model(VLAN))
    tag_sync_from_forward.content_types.add(ContentType.objects.get_for_model(VRF))
    tag_sync_from_forward.content_types.add(ContentType.objects.get_for_model(Prefix))

    # Ensure the Status is set to apply to the Device model
    device_status = Status.objects.get(name=constants.DEFAULT_DEVICE_STATUS)
    device_status.content_types.add(device_content_type)
