"""Signals for Device42 integration."""

from nautobot.core.signals import nautobot_database_ready


def register_signals(sender):
    """Register signals for IPFabric integration."""
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)


# pylint: disable=unused-argument, invalid-name
def nautobot_database_ready_callback(sender, *, apps, **kwargs):
    """Ensure Site LocationType created and configured correctly.

    Callback function triggered by the nautobot_database_ready signal when the Nautobot database is fully ready.
    """
    ContentType = apps.get_model("contenttypes", "ContentType")
    Device = apps.get_model("dcim", "Device")
    Site = apps.get_model("dcim", "Location")
    RackGroup = apps.get_model("dcim", "RackGroup")
    Rack = apps.get_model("dcim", "Rack")
    Prefix = apps.get_model("ipam", "Prefix")
    VLAN = apps.get_model("ipam", "VLAN")
    LocationType = apps.get_model("dcim", "LocationType")
    VirtualChassis = apps.get_model("dcim", "VirtualChassis")

    loc_type = LocationType.objects.update_or_create(name="Site")[0]
    for obj_type in [Site, RackGroup, Rack, Device, VirtualChassis, Prefix, VLAN]:
        loc_type.content_types.add(ContentType.objects.get_for_model(obj_type))
    loc_type.save()
