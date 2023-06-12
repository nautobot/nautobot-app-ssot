"""Signal handlers for nautobot_ssot_servicenow."""

from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.utilities.choices import ColorChoices


def nautobot_database_ready_callback(sender, *, apps, **kwargs):  # pylint: disable=unused-argument
    """Callback function triggered by the nautobot_database_ready signal when the Nautobot database is fully ready."""
    # pylint: disable=invalid-name
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    Device = apps.get_model("dcim", "Device")
    DeviceType = apps.get_model("dcim", "DeviceType")
    Interface = apps.get_model("dcim", "Interface")
    Manufacturer = apps.get_model("dcim", "Manufacturer")
    Region = apps.get_model("dcim", "Region")
    Site = apps.get_model("dcim", "Site")
    Tag = apps.get_model("extras", "Tag")

    Tag.objects.get_or_create(
        slug="ssot-synced-to-servicenow",
        defaults={
            "name": "SSoT Synced to ServiceNow",
            "description": "Object synced at some point from Nautobot to ServiceNow",
            "color": ColorChoices.COLOR_LIGHT_GREEN,
        },
    )
    custom_field, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_DATE,
        name="ssot-synced-to-servicenow",
        defaults={
            "label": "Last synced to ServiceNow on",
        },
    )
    for content_type in [
        ContentType.objects.get_for_model(Device),
        ContentType.objects.get_for_model(DeviceType),
        ContentType.objects.get_for_model(Interface),
        ContentType.objects.get_for_model(Manufacturer),
        ContentType.objects.get_for_model(Region),
        ContentType.objects.get_for_model(Site),
    ]:
        custom_field.content_types.add(content_type)
