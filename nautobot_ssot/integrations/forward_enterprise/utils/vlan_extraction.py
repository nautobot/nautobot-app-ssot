"""Utilities for extracting VLAN information from Forward Enterprise data."""

import re
from typing import Dict, Optional, Set

from nautobot_ssot.integrations.forward_enterprise import constants

try:
    from diffsync.exceptions import ObjectNotFound
except ImportError:
    # Fallback if diffsync is not available
    class ObjectNotFound(Exception):
        """Fallback ObjectNotFound exception."""


def extract_vlan_id_from_interface(interface_name: str) -> Optional[int]:
    """Extract VLAN ID from interface name using various patterns."""
    if not interface_name:
        return None

    interface_lower = interface_name.lower()

    # Common VLAN interface patterns
    patterns = [
        r"vlan(\d+)",  # vlan100, Vlan100
        r"vl(\d+)",  # vl100
        r"\.(\d+)$",  # GigE0/0/1.100 (subinterface)
        r"/(\d+)$",  # interface/100
    ]

    for pattern in patterns:
        match = re.search(pattern, interface_lower)
        if match:
            try:
                vlan_id = int(match.group(1))
                # Validate VLAN ID range using constants
                if constants.MIN_VLAN_ID <= vlan_id <= constants.MAX_VLAN_ID:
                    return vlan_id
            except ValueError:
                continue

    return None


def extract_vlans_by_location(adapter) -> Dict[str, Set[int]]:
    """Extract VLANs from interface data, grouped by device location."""
    vlans_by_location = {}
    skipped_devices = set()

    # Extract VLANs from interface names, grouped by device location
    for interface_data in getattr(adapter, "interfaces_data", []):
        interface_name = interface_data.get("name", "")
        device_name = interface_data.get("device", "")

        # Extract VLAN ID from various interface naming patterns
        vlan_id = extract_vlan_id_from_interface(interface_name)
        if vlan_id and device_name:
            # Get device location from our loaded devices
            device_location = get_device_location(adapter, device_name)

            if device_location is None:
                # Device wasn't loaded - skip this VLAN and track the device
                if device_name not in skipped_devices:
                    skipped_devices.add(device_name)
                continue

            if device_location not in vlans_by_location:
                vlans_by_location[device_location] = set()
            vlans_by_location[device_location].add(vlan_id)

    # Extract VLANs from IPAM data interface names as well
    for ipam_record in getattr(adapter, "ipam_data", []):
        interface_name = ipam_record.get("interface", "")
        device_name = ipam_record.get("device", "")

        vlan_id = extract_vlan_id_from_interface(interface_name)
        if vlan_id and device_name:
            # Get device location from our loaded devices
            device_location = get_device_location(adapter, device_name)

            if device_location is None:
                # Device wasn't loaded - skip this VLAN and track the device
                if device_name not in skipped_devices:
                    skipped_devices.add(device_name)
                continue

            if device_location not in vlans_by_location:
                vlans_by_location[device_location] = set()
            vlans_by_location[device_location].add(vlan_id)

    # Log any devices that were skipped due to not being loaded
    if skipped_devices and hasattr(adapter, "job") and adapter.job:
        adapter.job.logger.warning(
            f"Skipped VLAN extraction for {len(skipped_devices)} devices that were not loaded: {', '.join(sorted(skipped_devices))}"
        )

    return vlans_by_location


def get_device_location(adapter, device_name: str) -> Optional[str]:
    """Get the location for a device, with fallback to raw device data lookup.

    Returns None if device cannot be found anywhere, indicating it wasn't loaded.
    """
    # First try to get from loaded DiffSync devices
    try:
        device_obj = adapter.get("device", {"name": device_name})
        return device_obj.location__name
    except (KeyError, ObjectNotFound):
        pass

    # Fallback to checking raw device data
    if hasattr(adapter, "devices_data"):
        for device_data in adapter.devices_data:
            if device_data.get("name") == device_name:
                location = device_data.get("location")
                if location and location.lower() != "unknown":
                    return location

    # Device not found in loaded data - this indicates the device wasn't loaded/created
    return None


def create_vlan_group_name(location_name: str) -> str:
    """Create a standardized VLAN group name for a location."""
    return constants.VLAN_GROUP_NAME_TEMPLATE.format(location_name=location_name)
