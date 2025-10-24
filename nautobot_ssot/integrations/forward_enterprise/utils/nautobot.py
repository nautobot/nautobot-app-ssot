"""Utility functions for working with Nautobot objects in Forward Enterprise integration."""

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer, Platform
from nautobot.extras.models import Role, Status
from nautobot.ipam.models import VRF, Namespace, VLANGroup

from nautobot_ssot.integrations.forward_enterprise import constants


def get_status(name: str) -> Status:
    """Retrieve a Status by name."""
    try:
        return Status.objects.get(name=name)
    except ObjectDoesNotExist:
        # Return a default status if not found
        return Status.objects.get(name="Active")


def normalize_interface_type(interface_type: str) -> str:
    """Normalize interface types to match Nautobot choices."""
    if not interface_type:
        return "other"

    # Use the interface type mapping from constants
    normalized = interface_type.lower().replace(" ", "").replace("-", "")
    return constants.INTERFACE_TYPE_MAP.get(normalized, "other")


def get_default_device_role() -> str:
    """Get the default device role for Forward Enterprise devices."""
    return constants.DEFAULT_DEVICE_ROLE


def get_default_device_status() -> str:
    """Get the default device status for Forward Enterprise devices."""
    return constants.DEFAULT_DEVICE_STATUS


def get_default_interface_status() -> str:
    """Get the default interface status for Forward Enterprise interfaces."""
    return constants.DEFAULT_INTERFACE_STATUS


def prefetch_nautobot_objects():
    """Prefetch commonly accessed objects to warm up Django ORM caches."""
    # Bulk prefetch with efficient queries
    list(Manufacturer.objects.all())
    list(DeviceType.objects.select_related("manufacturer").all())
    list(Role.objects.all())
    list(Status.objects.all())
    list(Location.objects.all())
    list(Platform.objects.select_related("manufacturer").all())
    list(VRF.objects.select_related("namespace").all())
    list(Namespace.objects.all())


def ensure_device_content_type_on_location_type(location_type_name: str = "Site"):
    """Ensure that Device content type is added to the specified location type.

    This allows devices to be assigned to locations of this type.
    If the location type doesn't exist, it will be created.

    Args:
        location_type_name (str): The name of the location type to update. Defaults to "Site".
    """
    try:
        device_content_type = ContentType.objects.get_for_model(Device)
        location_content_type = ContentType.objects.get_for_model(Location)

        # Get or create the location type
        location_type, _ = LocationType.objects.get_or_create(
            name=location_type_name,
            defaults={
                "description": f"Location type created by Forward Enterprise integration",
            },
        )

        # Ensure Device content type is enabled
        if device_content_type not in location_type.content_types.all():
            location_type.content_types.add(device_content_type)

        # Ensure Location content type is enabled (locations can have parent locations)
        if location_content_type not in location_type.content_types.all():
            location_type.content_types.add(location_content_type)

        location_type.save()

    except ContentType.DoesNotExist:
        # If content type doesn't exist, we'll skip this step
        pass


def ensure_vlan_group_content_type_on_location_type(location_type_name: str = "Site"):
    """Ensure that VLANGroup content type is added to the specified location type.

    Args:
        location_type_name (str): The name of the location type to update. Defaults to "Site".
    """
    try:
        location_type = LocationType.objects.get(name=location_type_name)
        vlan_group_content_type = ContentType.objects.get_for_model(VLANGroup)

        if vlan_group_content_type not in location_type.content_types.all():
            location_type.content_types.add(vlan_group_content_type)
            location_type.save()

    except (LocationType.DoesNotExist, ContentType.DoesNotExist):
        # If location type or content type doesn't exist, we'll skip this step
        pass
