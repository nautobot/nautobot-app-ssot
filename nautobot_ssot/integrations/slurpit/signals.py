# pylint: disable=duplicate-code
"""Signal handlers for Slurpit integration."""

from typing import List, Optional

from nautobot.core.choices import ColorChoices
from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import CustomFieldTypeChoices


def register_signals(sender):
    """Register signals for Slurpit integration."""
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)


def create_custom_field(key: str, label: str, models: List, apps, cf_type: Optional[str] = "type_date"):
    """Create custom field on a given model instance type.

    Args:
        key (str): Natural key
        label (str): Label description
        models (List): List of Django Models
        apps: Django Apps
        cf_type: (str, optional): Type of Field. Supports 'type_text' or 'type_date'. Defaults to 'type_date'.
    """
    ContentType = apps.get_model("contenttypes", "ContentType")  # pylint:disable=invalid-name
    CustomField = apps.get_model("extras", "CustomField")  # pylint:disable=invalid-name
    if cf_type == "type_date":
        custom_field, _ = CustomField.objects.get_or_create(
            key=key,
            type=CustomFieldTypeChoices.TYPE_DATE,
            label=label,
        )
    else:
        custom_field, _ = CustomField.objects.get_or_create(
            key=key,
            type=CustomFieldTypeChoices.TYPE_TEXT,
            label=label,
        )
    for model in models:
        custom_field.content_types.add(ContentType.objects.get_for_model(model))
    custom_field.save()


def nautobot_database_ready_callback(sender, *, apps, **kwargs):  # pylint: disable=unused-argument
    """Callback function triggered by the nautobot_database_ready signal when the Nautobot database is fully ready."""
    # pylint: disable=invalid-name, too-many-locals
    Device = apps.get_model("dcim", "Device")
    DeviceType = apps.get_model("dcim", "DeviceType")
    Manufacturer = apps.get_model("dcim", "Manufacturer")
    Platform = apps.get_model("dcim", "Platform")
    Role = apps.get_model("extras", "Role")
    InventoryItem = apps.get_model("dcim", "InventoryItem")
    Interface = apps.get_model("dcim", "Interface")
    IPAddress = apps.get_model("ipam", "IPAddress")
    Location = apps.get_model("dcim", "Location")
    VLAN = apps.get_model("ipam", "VLAN")
    VRF = apps.get_model("ipam", "VRF")
    Prefix = apps.get_model("ipam", "Prefix")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Tag = apps.get_model("extras", "Tag")

    synced_tag, _ = Tag.objects.get_or_create(
        name="SSoT Synced from Slurpit",
        defaults={
            "description": "Object synced at some point from Slurpit to Nautobot",
            "color": ColorChoices.COLOR_LIGHT_GREEN,
        },
    )
    synced_tag.content_types.add(ContentType.objects.get_for_model(Device))
    synced_tag.content_types.add(ContentType.objects.get_for_model(DeviceType))
    synced_tag.content_types.add(ContentType.objects.get_for_model(InventoryItem))
    synced_tag.content_types.add(ContentType.objects.get_for_model(Interface))
    synced_tag.content_types.add(ContentType.objects.get_for_model(IPAddress))
    synced_tag.content_types.add(ContentType.objects.get_for_model(Location))
    synced_tag.content_types.add(ContentType.objects.get_for_model(VLAN))
    synced_tag.content_types.add(ContentType.objects.get_for_model(VRF))
    synced_tag.content_types.add(ContentType.objects.get_for_model(Prefix))

    Tag.objects.get_or_create(
        name="SSoT Safe Delete",
        defaults={
            "description": "Safe Delete Mode tag to flag an object, but not delete from Nautobot.",
            "color": ColorChoices.COLOR_RED,
        },
    )
    synced_from_models = [
        Device,
        DeviceType,
        InventoryItem,
        Interface,
        IPAddress,
        Location,
        VLAN,
        VRF,
        Prefix,
        Manufacturer,
        Platform,
        Role,
    ]
    create_custom_field("system_of_record", "System of Record", synced_from_models, apps=apps, cf_type="type_text")
    create_custom_field("last_synced_from_sor", "Last sync from System of Record", synced_from_models, apps=apps)
