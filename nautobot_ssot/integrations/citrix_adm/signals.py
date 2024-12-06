"""Signals triggered when Nautobot starts to perform certain actions."""

from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import CustomFieldTypeChoices

from nautobot_ssot.utils import create_or_update_custom_field


def register_signals(sender):
    """Register signals for IPFabric integration."""
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)


def nautobot_database_ready_callback(sender, *, apps, **kwargs):  # pylint: disable=unused-argument
    """Ensure the Citrix Manufacturer is in place for DeviceTypes to use. Adds OS Version CustomField to Devices and System of Record and Last Sync'd to Site, Device, Interface, and IPAddress.

    Callback function triggered by the nautobot_database_ready signal when the Nautobot database is fully ready.
    """
    # pylint: disable=invalid-name, too-many-locals
    ContentType = apps.get_model("contenttypes", "ContentType")
    Manufacturer = apps.get_model("dcim", "Manufacturer")
    Device = apps.get_model("dcim", "Device")
    Interface = apps.get_model("dcim", "Interface")
    Prefix = apps.get_model("ipam", "Prefix")
    IPAddress = apps.get_model("ipam", "IPAddress")
    Platform = apps.get_model("dcim", "Platform")

    citrix_manu, _ = Manufacturer.objects.update_or_create(name="Citrix")
    Platform.objects.update_or_create(
        name="citrix.adc",
        defaults={
            "name": "citrix.adc",
            "napalm_driver": "netscaler",
            "manufacturer": citrix_manu,
            "network_driver": "citrix_netscaler",
        },
    )
    ha_node_field, _ = create_or_update_custom_field(
        apps, key="ha_node", field_type=CustomFieldTypeChoices.TYPE_TEXT, label="HA Node"
    )
    ha_node_field.content_types.add(ContentType.objects.get_for_model(Device))

    sor_custom_field = create_or_update_custom_field(
        apps, key="system_of_record", field_type=CustomFieldTypeChoices.TYPE_TEXT, label="System of Record"
    )[0]
    sync_custom_field = create_or_update_custom_field(
        apps,
        key="last_synced_from_sor",
        field_type=CustomFieldTypeChoices.TYPE_DATE,
        label="Last sync from System of Record",
    )[0]

    for model in [Device, Interface, Prefix, IPAddress]:
        sor_custom_field.content_types.add(ContentType.objects.get_for_model(model))
        sync_custom_field.content_types.add(ContentType.objects.get_for_model(model))
