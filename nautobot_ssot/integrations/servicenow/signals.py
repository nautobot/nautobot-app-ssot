# pylint: disable=duplicate-code
"""Signal handlers for ServiceNow integration."""

from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.core.choices import ColorChoices


def register_signals(sender):
    """Register signals for ServiceNow integration."""
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)


def nautobot_database_ready_callback(sender, *, apps, **kwargs):  # pylint: disable=unused-argument
    """Callback function triggered by the nautobot_database_ready signal when the Nautobot database is fully ready."""
    # pylint: disable=invalid-name
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    Device = apps.get_model("dcim", "Device")
    DeviceType = apps.get_model("dcim", "DeviceType")
    Interface = apps.get_model("dcim", "Interface")
    Manufacturer = apps.get_model("dcim", "Manufacturer")
    Location = apps.get_model("dcim", "Location")
    Tag = apps.get_model("extras", "Tag")

    Tag.objects.get_or_create(
        name="SSoT Synced to ServiceNow",
        defaults={
            "name": "SSoT Synced to ServiceNow",
            "description": "Object synced at some point from Nautobot to ServiceNow",
            "color": ColorChoices.COLOR_LIGHT_GREEN,
        },
    )
    custom_field, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_DATE,
        key="ssot_synced_to_servicenow",
        defaults={
            "label": "Last synced to ServiceNow",
        },
    )
    for content_type in [
        ContentType.objects.get_for_model(Device),
        ContentType.objects.get_for_model(DeviceType),
        ContentType.objects.get_for_model(Interface),
        ContentType.objects.get_for_model(Manufacturer),
        ContentType.objects.get_for_model(Location),
    ]:
        custom_field.content_types.add(content_type)
