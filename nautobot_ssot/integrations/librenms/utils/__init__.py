"""Utility functions for working with LibreNMS and Nautobot."""

import inspect
import ipaddress
import logging
import os

from constance import config as constance_name
from django.conf import settings

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


def normalize_device_hostname(hostname):
    """Normalize device hostname to be a valid LibreNMS or Nautobot hostname. Remove domain suffixes and uppercase the names for comparison (if not an IP Address)."""
    if isinstance(hostname, ipaddress.IPv4Address) or isinstance(hostname, ipaddress.IPv6Address):
        return hostname
    hostname = hostname.split(".")[0]
    return hostname.upper()


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
