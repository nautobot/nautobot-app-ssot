"""Utility functions for location handling and normalization in Forward Enterprise integration."""

from django.core.exceptions import ValidationError
from nautobot.dcim.models import Location, LocationType
from nautobot.extras.models import Status


def get_or_create_location_for_vlan_group(location_name, adapter_job=None):
    """
    Get or create a location for VLAN group assignment.

    Args:
        location_name (str): Name of the location to get or create
        adapter_job: Optional job instance for logging

    Returns:
        tuple: (location_object, created_boolean) or (None, False) if failed
    """
    if not location_name:
        return None, False

    try:
        # Get location type and status
        location_type, _ = LocationType.objects.get_or_create(
            name="Site", defaults={"description": "Site location type for SSoT"}
        )
        status = Status.objects.get(name="Active")

        location, location_created = Location.objects.get_or_create(
            name=location_name,
            defaults={
                "location_type": location_type,
                "status": status,
                "description": f"Location imported from Forward Enterprise: {location_name}",
            },
        )

        if location_created and adapter_job:
            adapter_job.logger.info("Created location '%s' for VLAN group", location_name)
        elif adapter_job:
            adapter_job.logger.debug("Found existing location '%s' for VLAN group", location_name)

        return location, location_created

    except (ValidationError, ValueError, TypeError) as e:
        if adapter_job:
            adapter_job.logger.warning("Could not create/find location '%s': %s", location_name, e)
        return None, False
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        if adapter_job:
            adapter_job.logger.error(f"Unexpected error handling location '{location_name}': {exc}")
        return None, False


def extract_location_from_vlan_group_name(vlan_group_name):
    """
    Extract location name from VLAN group name.

    Args:
        vlan_group_name (str): VLAN group name (e.g. "Forward Enterprise - compute-pod200")

    Returns:
        str or None: Location name or None if not found
    """
    if not vlan_group_name or " - " not in vlan_group_name:
        return None

    return vlan_group_name.split(" - ", 1)[1]


def normalize_location_name(name):
    """Normalize location name to a canonical value for SSoT/Forward Enterprise."""
    if name is None:
        return "Unknown"
    s = str(name).strip()
    return "Unknown" if s.lower() in ("", "unknown", "null", "none") else s
