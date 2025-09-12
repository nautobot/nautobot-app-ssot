"""Utility functions for working with LibreNMS and Nautobot."""

# pylint: disable=duplicate-code

import inspect
import ipaddress
import logging
import os
import re

from constance import config as constance_name
from django.conf import settings

from nautobot_ssot.integrations.librenms.constants import os_manufacturer_map

LOGGER = logging.getLogger(__name__)


def normalize_gps_coordinates(gps_coord):
    """Normalize GPS Coordinates to 6 decimal places which is all that is stored in Nautobot."""
    return round(float(gps_coord), 6)


def normalize_setting(variable_name):
    """Get a value from Django settings (if specified there) or Constance configuration (otherwise)."""
    # Explicitly set in settings.py or nautobot_config.py takes precedence, for now
    if variable_name.lower() in settings.PLUGINS_CONFIG["nautobot_ssot"]:
        return settings.PLUGINS_CONFIG["nautobot_ssot"][variable_name.lower()]
    return getattr(constance_name, f"{variable_name.upper()}")


def normalize_device_hostname(device, job):
    """Normalize device hostname to be a valid LibreNMS or Nautobot hostname. Remove domain suffixes and uppercase the names for comparison (if not an IP Address)."""
    # Handle case where device is a string (from Nautobot) vs dictionary (from LibreNMS)
    if isinstance(device, str):
        hostname_str = device
    else:
        hostname_str = device[job.hostname_field]

    try:
        hostname = ipaddress.ip_address(hostname_str)
        if not settings.PLUGINS_CONFIG["nautobot_ssot"]["librenms_allow_ip_hostnames"]:
            if isinstance(device, dict):
                if "load_errors" not in device:
                    device["load_errors"] = []
                device["load_errors"].append("The hostname cannot be an IP Address")
            return None
    except ValueError:
        hostname = hostname_str.split(".")[0].upper()
    return str(hostname)


def parse_hostname_for_location(location_map: dict[str, dict[str, str]], device_hostname: str, device_location: str) -> dict:
    """Parse device hostname from location_map to get Device Location.

    Args:
        location_map (dict[str, dict[str, str]]): Dictionary of locations.
        device_hostname (str): Hostname of Device to determine location of.

    Returns:
        dict: Dictionary of DeviceLocation data. Includes location name and parent location name.
    """
    if location_map:  # pylint: disable=duplicate-code
        # Handle case where location_map might be a JSON string
        if isinstance(location_map, str):
            try:
                import json
                location_map = json.loads(location_map)
            except (json.JSONDecodeError, TypeError):
                # If it's not valid JSON, treat as empty
                location_map = None
        
        if location_map:
            # Handle dictionary format where key is pattern and value contains Name/Parent
            if isinstance(location_map, dict):
                for pattern, mapping in location_map.items():
                    # Make pattern matching case-insensitive
                    match = re.match(pattern=pattern, string=device_hostname, flags=re.IGNORECASE)
                    if match:
                        device_location_data = {
                            "name": mapping.get("Name"),
                            "parent": mapping.get("Parent"),
                        }
                        return device_location_data
            # Handle list of mappings format (legacy format)
            elif isinstance(location_map, list):
                for entry in location_map:
                    if isinstance(entry, dict) and "prefix" in entry:
                        # Use the prefix as the regex pattern
                        pattern = entry["prefix"]
                        match = re.match(pattern=pattern, string=device_hostname, flags=re.IGNORECASE)
                        if match:
                            device_location_data = {
                                "name": entry["location"],
                                "parent": entry.get("parent", None),
                            }
                            return device_location_data
        
        # If no match found in location_map, fall back to device_location
        device_location_data = {
            "name": device_location,
            "parent": None,
        }
    else:
        device_location_data = {
            "name": device_location,
            "parent": None,
        }

    return device_location_data


def has_required_values(device, job):
    """Check if the device has required values."""
    # Ensure device is a dictionary
    if not isinstance(device, dict):
        return False
        
    required_values = [job.hostname_field, "location", "type", "os", "hardware"]
    for value in required_values:
        if value not in device or not isinstance(device[value], str) or device[value] == "":
            if "load_errors" not in device:
                device["load_errors"] = []
            device["load_errors"].append(f"{value} string is required")

    # Check if manufacturer mapping exists for the OS
    if "os" in device and device["os"]:
        if os_manufacturer_map.get(device["os"]) is None:
            if "load_errors" not in device:
                device["load_errors"] = []
            device["load_errors"].append(f"Manufacturer mapping not found for OS: {device['os']}")

    if len(device.get("load_errors", [])) > 0:
        return False
    return True


def check_sor_field(model):
    """Check if the System of Record field is present and is set to "LibreNMS"."""
    return (
        "system_of_record" in model.custom_field_data
        and model.custom_field_data["system_of_record"] is not None
        and os.getenv("NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD", "LibreNMS")
        in model.custom_field_data["system_of_record"]
    )


def get_sor_field_nautobot_object(nb_object):
    """Get the System of Record field from an object."""
    _sor = ""
    if "system_of_record" in nb_object.custom_field_data:
        _sor = (
            nb_object.custom_field_data["system_of_record"]
            if nb_object.custom_field_data["system_of_record"] is not None
            else ""
        )
    return _sor


def is_running_tests():
    """Check whether running unittests or actual job."""
    for frame in inspect.stack():
        if frame.filename.endswith("unittest/case.py"):
            return True
    return False
