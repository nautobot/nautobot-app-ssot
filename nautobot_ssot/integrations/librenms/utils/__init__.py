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


def has_required_values(device, job):
    """Check if the device has required values."""
    # Ensure device is a dictionary
    if not isinstance(device, dict):
        return False

    required_values_dict = {
        job.hostname_field: True,
        "location": True,
        "role": True,
        "platform": True,
        "device_type": True,
    }

    unpermitted_values = job.unpermitted_values

    for key in required_values_dict:
        if key not in device or not isinstance(device[key], str) or device[key] in [None, ""]:
            if "load_errors" not in device:
                device["load_errors"] = []
            device["load_errors"].append(f"{key} string is required")
            required_values_dict[key] = False
        if unpermitted_values is not None and device.get(key) in unpermitted_values:
            if "load_errors" not in device:
                device["load_errors"] = []
            device["load_errors"].append(f"{key} cannot be '{device[key]}'")
            required_values_dict[key] = False

    # Check if manufacturer mapping exists for the OS
    if "platform" in device and device["platform"]:
        if os_manufacturer_map.get(device["platform"]) is None:
            if "load_errors" not in device:
                device["load_errors"] = []
            device["load_errors"].append(f"Manufacturer mapping not found for OS: {device['platform']}")
            required_values_dict["platform"] = False

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
