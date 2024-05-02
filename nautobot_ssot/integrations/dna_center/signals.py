"""Signals triggered when Nautobot starts to perform certain actions."""

from nautobot.extras.choices import CustomFieldTypeChoices


def nautobot_database_ready_callback(sender, *, apps, **kwargs):  # pylint: disable=unused-argument, too-many-locals
    """Create CustomField to note System of Record for SSoT.

    Callback function triggered by the nautobot_database_ready signal when the Nautobot database is fully ready.
    """
    # pylint: disable=invalid-name
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    LocationType = apps.get_model("dcim", "LocationType")
    Device = apps.get_model("dcim", "Device")
    Rack = apps.get_model("dcim", "Rack")
    RackGroup = apps.get_model("dcim", "RackGroup")
    Interface = apps.get_model("dcim", "Interface")
    IPAddress = apps.get_model("ipam", "IPAddress")
    Prefix = apps.get_model("ipam", "Prefix")

    region = LocationType.objects.update_or_create(name="Region", defaults={"nestable": True})[0]
    region.content_types.add(ContentType.objects.get_for_model(Device))
    site = LocationType.objects.update_or_create(name="Site", defaults={"nestable": False, "parent": region})[0]
    site.content_types.add(ContentType.objects.get_for_model(Device))
    floor = LocationType.objects.update_or_create(name="Floor", defaults={"nestable": False, "parent": site})[0]
    floor.content_types.add(ContentType.objects.get_for_model(Device))

    ver_dict = {
        "key": "os_version",
        "type": CustomFieldTypeChoices.TYPE_TEXT,
        "label": "OS Version",
    }
    ver_field, _ = CustomField.objects.get_or_create(key=ver_dict["key"], defaults=ver_dict)
    ver_field.content_types.add(ContentType.objects.get_for_model(Device))
    sor_cf_dict = {
        "type": CustomFieldTypeChoices.TYPE_TEXT,
        "key": "system_of_record",
        "label": "System of Record",
    }
    sor_custom_field, _ = CustomField.objects.update_or_create(key=sor_cf_dict["key"], defaults=sor_cf_dict)
    sync_cf_dict = {
        "type": CustomFieldTypeChoices.TYPE_DATE,
        "key": "ssot_last_synchronized",
        "label": "Last sync from System of Record",
    }
    sync_custom_field, _ = CustomField.objects.update_or_create(key=sync_cf_dict["key"], defaults=sync_cf_dict)
    for model in [Device, Interface, IPAddress, Prefix, Rack, RackGroup]:
        sor_custom_field.content_types.add(ContentType.objects.get_for_model(model))
        sync_custom_field.content_types.add(ContentType.objects.get_for_model(model))
