"""Signals triggered when Nautobot starts to perform certain actions."""

from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import CustomFieldTypeChoices

try:
    from nautobot.extras.models.metadata import MetadataTypeDataTypeChoices

except ImportError:
    pass


def register_signals(sender):
    """Register signals for DNA Center integration."""
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)


def nautobot_database_ready_callback(sender, *, apps, **kwargs):  # pylint: disable=unused-argument, too-many-locals
    """Create CustomField to note System of Record for SSoT.

    Callback function triggered by the nautobot_database_ready signal when the Nautobot database is fully ready.
    """
    # pylint: disable=invalid-name
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    Location = apps.get_model("dcim", "Location")
    Device = apps.get_model("dcim", "Device")
    Interface = apps.get_model("dcim", "Interface")
    IPAddress = apps.get_model("ipam", "IPAddress")
    IPAddressToInterface = apps.get_model("ipam", "IPAddressToInterface")
    Prefix = apps.get_model("ipam", "Prefix")

    sor_cf_dict = {
        "type": CustomFieldTypeChoices.TYPE_TEXT,
        "key": "system_of_record",
        "label": "System of Record",
    }
    sor_custom_field, _ = CustomField.objects.update_or_create(key=sor_cf_dict["key"], defaults=sor_cf_dict)
    sync_cf_dict = {
        "type": CustomFieldTypeChoices.TYPE_DATE,
        "key": "last_synced_from_sor",
        "label": "Last sync from System of Record",
    }
    sync_custom_field, _ = CustomField.objects.update_or_create(key=sync_cf_dict["key"], defaults=sync_cf_dict)
    for model in [Device, Interface, IPAddress, Prefix]:
        sor_custom_field.content_types.add(ContentType.objects.get_for_model(model))
        sync_custom_field.content_types.add(ContentType.objects.get_for_model(model))

    try:
        # create Metadata objects for DNA Center integration
        MetadataType = apps.get_model("extras", "MetadataType")
        last_sync_type = MetadataType.objects.get_or_create(
            name="Last Sync from DNA Center", defaults={
            "description": "Describes the last date that a object's field was updated from DNA Center.",
            "data_type": MetadataTypeDataTypeChoices.TYPE_DATE
        }
        )
        last_sync_type.save()
        for _model in [Location, Device, Interface, IPAddress, IPAddressToInterface, Prefix]:
            last_sync_type.content_types.add(ContentType.objects.get_for_model(_model))
    except LookupError:
        print("Unable to find MetadataType model. Skipping MetadataType creation.")
