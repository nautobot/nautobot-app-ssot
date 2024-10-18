"""Signals triggered when Nautobot starts to perform certain actions."""

from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import CustomFieldTypeChoices


def register_signals(sender):
    """Register signals for DNA Center integration."""
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)


def nautobot_database_ready_callback(sender, *, apps, **kwargs):  # pylint: disable=unused-argument
    """Adds OS Version and Physical Address CustomField to Devices and System of Record and Last Sync'd to Device, and IPAddress.

    Callback function triggered by the nautobot_database_ready signal when the Nautobot database is fully ready.
    """
    # pylint: disable=invalid-name, too-many-locals
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    Device = apps.get_model("dcim", "Device")
    Interface = apps.get_model("dcim", "Interface")
    Prefix = apps.get_model("ipam", "Prefix")
    IPAddress = apps.get_model("ipam", "IPAddress")
    Manufacturer = apps.get_model("dcim", "Manufacturer")
    Platform = apps.get_model("dcim", "Platform")

    cisco_manu = Manufacturer.objects.get_or_create(name="Cisco Meraki")[0]
    plat_dict = {
        "name": "Cisco Meraki",
        "manufacturer": cisco_manu,
        "network_driver": "cisco_meraki",
    }
    Platform.objects.update_or_create(name__icontains="Meraki", defaults=plat_dict)

    sysrecord_cf_dict = {
        "type": CustomFieldTypeChoices.TYPE_TEXT,
        "key": "system_of_record",
        "label": "System of Record",
    }
    sysrecord_custom_field, _ = CustomField.objects.update_or_create(
        key=sysrecord_cf_dict["key"], defaults=sysrecord_cf_dict
    )
    last_sync_cf_dict = {
        "type": CustomFieldTypeChoices.TYPE_DATE,
        "key": "last_synced_from_sor",
        "label": "Last sync from System of Record",
    }
    last_sync_custom_field, _ = CustomField.objects.update_or_create(
        key=last_sync_cf_dict["key"], defaults=last_sync_cf_dict
    )
    for model in [Device, Interface, Prefix, IPAddress]:
        sysrecord_custom_field.content_types.add(ContentType.objects.get_for_model(model))
        last_sync_custom_field.content_types.add(ContentType.objects.get_for_model(model))
