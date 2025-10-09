"""Utility functions for working with LibreNMS and Nautobot."""

# pylint: disable=duplicate-code

import inspect
import ipaddress
import json
import logging
import os

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
        hostname_str = device.get(getattr(job, "hostname_field", "hostname"), "")

    try:
        hostname = ipaddress.ip_address(hostname_str)
        if not settings.PLUGINS_CONFIG["nautobot_ssot"]["librenms_allow_ip_hostnames"]:
            return {"valid": False, "reason": "The hostname cannot be an IP Address"}
    except ValueError:
        hostname = hostname_str.split(".")[0].upper()
    return str(hostname)


def has_required_values(device, job):
    """Check if the device has required values."""
    hostname_field = getattr(job, "hostname_field", "hostname")
    required_values_dict = {
        hostname_field: {"valid": True},
        "location": {"valid": True},
        "role": {"valid": True},
        "platform": {"valid": True},
        "device_type": {"valid": True},
    }

    unpermitted_values = getattr(job, "unpermitted_values", None)
    
    # Convert JSONVar to proper data type if needed
    if unpermitted_values and hasattr(unpermitted_values, '__str__') and not isinstance(unpermitted_values, list):
        try:
            unpermitted_values = json.loads(str(unpermitted_values))
        except (json.JSONDecodeError, TypeError):
            # If it's not valid JSON, treat as None
            unpermitted_values = None

    for key in required_values_dict:
        if key in device and isinstance(device[key], dict) and device[key].get("reason"):
            required_values_dict[key] = device[key]
            continue
        if key not in device or not isinstance(device.get(key), str) or device.get(key) in [None, ""]:
            required_values_dict[key]["valid"] = False
            required_values_dict[key]["reason"] = "String is required"
            continue
        if unpermitted_values and device.get(key) in unpermitted_values:
            required_values_dict[key]["valid"] = False
            required_values_dict[key]["reason"] = f"{key} cannot be '{device[key]}'"
            continue
        if key == "platform" and device.get(key) not in os_manufacturer_map:
            required_values_dict[key]["valid"] = False
            required_values_dict[key]["reason"] = f"Manufacturer mapping not found for OS: {device[key]}"

    return required_values_dict


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
