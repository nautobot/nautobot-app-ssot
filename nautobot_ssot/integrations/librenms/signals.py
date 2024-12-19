"""Signals for LibreNMS SSoT."""

import importlib.util

from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import CustomFieldTypeChoices

from nautobot_ssot.utils import create_or_update_custom_field

LIFECYCLE_MGMT = bool(importlib.util.find_spec("nautobot_device_lifecycle_mgmt"))


def register_signals(sender):
    """Register signals for LibreNMS integration."""
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)


def nautobot_database_ready_callback(sender, *, apps, **kwargs):  # pylint: disable=unused-argument, too-many-statements
    """Adds OS Version and Physical Address CustomField to Devices and System of Record and Last Sync'd to Device, and IPAddress.

    Callback function triggered by the nautobot_database_ready signal when the Nautobot database is fully ready.
    """
    # pylint: disable=invalid-name, too-many-locals
    ContentType = apps.get_model("contenttypes", "ContentType")
    Manufacturer = apps.get_model("dcim", "Manufacturer")
    DeviceType = apps.get_model("dcim", "DeviceType")
    Device = apps.get_model("dcim", "Device")
    Interface = apps.get_model("dcim", "Interface")
    Platform = apps.get_model("dcim", "Platform")
    Location = apps.get_model("dcim", "Location")
    VLANGroup = apps.get_model("ipam", "VLANGroup")
    VLAN = apps.get_model("ipam", "VLAN")
    Prefix = apps.get_model("ipam", "Prefix")
    IPAddress = apps.get_model("ipam", "IPAddress")
    Role = apps.get_model("extras", "Role")
    Tag = apps.get_model("extras", "Tag")

    signal_to_model_mapping = {
        "manufacturer": Manufacturer,
        "device_type": DeviceType,
        "device": Device,
        "interface": Interface,
        "platform": Platform,
        "role": Role,
        "location": Location,
        "vlan_group": VLANGroup,
        "vlan": VLAN,
        "prefix": Prefix,
        "ip_address": IPAddress,
        "tag": Tag,
    }

    if LIFECYCLE_MGMT:
        try:
            SoftwareLCM = apps.get_model("nautobot_device_lifecycle_mgmt", "SoftwareLCM")
            signal_to_model_mapping["software"] = SoftwareLCM
        except LookupError as err:
            print(f"Unable to find SoftwareLCM model from Device Lifecycle Management App. {err}")
        try:
            SoftwareImageLCM = apps.get_model("nautobot_device_lifecycle_mgmt", "SoftwareImageLCM")
            signal_to_model_mapping["software_image"] = SoftwareImageLCM
        except LookupError as err:
            print(f"Unable to find SoftwareImageLCM model from Device Lifecycle Management App. {err}")
        try:
            ValidatedSoftwareLCM = apps.get_model("nautobot_device_lifecycle_mgmt", "ValidatedSoftwareLCM")
            signal_to_model_mapping["validated_software"] = ValidatedSoftwareLCM
        except LookupError as err:
            print(f"Unable to find ValidatedSoftwareLCM model from Device Lifecycle Management App. {err}")

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
    CustomField = apps.get_model("extras", "CustomField")  # pylint: disable=invalid-name
    device_id_cf_dict = {
        "type": CustomFieldTypeChoices.TYPE_INTEGER,
        "key": "librenms_device_id",
        "label": "LibreNMS Device ID",
        "default": None,
        "filter_logic": "exact",
    }
    device_id_custom_field, _ = CustomField.objects.update_or_create(
        key=device_id_cf_dict["key"], defaults=device_id_cf_dict
    )
    device_id_custom_field.content_types.add(ContentType.objects.get_for_model(signal_to_model_mapping["device"]))

    models_to_sync = [
        "device",
        "interface",
        "ip_address",
        "manufacturer",
        "device_type",
        "tag",
    ]
    try:
        for model in models_to_sync:
            model = ContentType.objects.get_for_model(signal_to_model_mapping[model])
            sor_custom_field.content_types.add(model.id)
            sync_custom_field.content_types.add(model.id)
    except Exception as e:
        print(f"Error occurred: {e}")
        raise
