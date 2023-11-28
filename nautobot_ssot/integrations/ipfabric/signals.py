# pylint: disable=duplicate-code
"""Signal handlers for IPFabric integration."""

from typing import List, Optional

from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.core.choices import ColorChoices


def register_signals(sender):
    """Register signals for IPFabric integration."""
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
    Role = apps.get_model("extras", "Role")
    Interface = apps.get_model("dcim", "Interface")
    IPAddress = apps.get_model("ipam", "IPAddress")
    Manufacturer = apps.get_model("dcim", "Manufacturer")
    Location = apps.get_model("dcim", "Location")
    VLAN = apps.get_model("ipam", "VLAN")
    Tag = apps.get_model("extras", "Tag")
    ContentType = apps.get_model("contenttypes", "ContentType")
    location_type = apps.get_model("dcim", "LocationType")

    Tag.objects.get_or_create(
        name="SSoT Synced from IPFabric",
        defaults={
            "description": "Object synced at some point from IPFabric to Nautobot",
            "color": ColorChoices.COLOR_LIGHT_GREEN,
        },
    )
    Tag.objects.get_or_create(
        name="SSoT Safe Delete",
        defaults={
            "description": "Safe Delete Mode tag to flag an object, but not delete from Nautobot.",
            "color": ColorChoices.COLOR_RED,
        },
    )
    loc_type, _ = location_type.objects.update_or_create(name="Site")
    loc_type.content_types.add(ContentType.objects.get_for_model(Device))
    loc_type.content_types.add(ContentType.objects.get_for_model(apps.get_model("ipam", "Prefix")))
    loc_type.content_types.add(ContentType.objects.get_for_model(VLAN))
    synced_from_models = [Device, DeviceType, Interface, Manufacturer, Location, VLAN, Role, IPAddress]
    create_custom_field("system_of_record", "System of Record", synced_from_models, apps=apps, cf_type="type_text")
    create_custom_field("last_synced_from_sor", "Last sync from System of Record", synced_from_models, apps=apps)
    create_custom_field("ipfabric_site_id", "IPFabric Location ID", [Location], apps=apps, cf_type="type_text")
    create_custom_field("ipfabric_type", "IPFabric Type", [Role], apps=apps, cf_type="type_text")
