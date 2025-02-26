# pylint: disable=R0801
"""Signals triggered when Nautobot starts to perform certain actions."""

from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import CustomFieldTypeChoices


def register_signals(sender):
    """Register signals for SolarWinds integration."""
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)


def nautobot_database_ready_callback(sender, *, apps, **kwargs):  # pylint: disable=unused-argument
    """Adds OS Version and Physical Address CustomField to Devices and System of Record and Last Sync'd to Device, and IPAddress.

    Callback function triggered by the nautobot_database_ready signal when the Nautobot database is fully ready.
    """
    # pylint: disable=invalid-name, too-many-locals
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    Device = apps.get_model("dcim", "Device")
    IPAddress = apps.get_model("ipam", "IPAddress")
    Prefix = apps.get_model("ipam", "Prefix")

    snmp_loc_dict = {
        "key": "snmp_location",
        "type": CustomFieldTypeChoices.TYPE_TEXT,
        "label": "SNMP Location",
    }
    snmp_loc_field, _ = CustomField.objects.get_or_create(key=snmp_loc_dict["key"], defaults=snmp_loc_dict)
    snmp_loc_field.content_types.add(ContentType.objects.get_for_model(Device))
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
    for model in [Device, IPAddress, Prefix]:
        sor_custom_field.content_types.add(ContentType.objects.get_for_model(model))
        sync_custom_field.content_types.add(ContentType.objects.get_for_model(model))
