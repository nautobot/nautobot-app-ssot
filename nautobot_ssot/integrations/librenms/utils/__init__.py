"""Utility functions for working with LibreNMS and Nautobot."""

import inspect
import logging
import os
import time

import requests
from constance import config as constance_name
from django.conf import settings

LOGGER = logging.getLogger(__name__)


def normalize_gps_coordinates(gps_coord):
    """Normalize GPS Coordinates to 6 decimal places which is all that is stored in Nautobot."""
    return round(gps_coord, 6)

def normalize_setting(variable_name):
    """Get a value from Django settings (if specified there) or Constance configuration (otherwise)."""
    # Explicitly set in settings.py or nautobot_config.py takes precedence, for now
    if variable_name.lower() in settings.PLUGINS_CONFIG["nautobot_ssot"]:
        return settings.PLUGINS_CONFIG["nautobot_ssot"][variable_name.lower()]
    return getattr(constance_name, f"{variable_name.upper()}")


def geocode_api_key():
    """Function to get near constant so the data is fresh for `geocode_api_key`."""
    return normalize_setting("librenms_geocode_api_key")


def get_city_state_geocode(latitude: str, longitude: str):
    """Lookup Geo information from latitude and longitude using GeoCode API."""
    api_key = geocode_api_key()
    if api_key:
        url = f"https://geocode.xyz/{latitude},{longitude}?json=1&auth={api_key}"
    else:
        # unauthenticated api limited to 1 request per second
        time.sleep(2)
        url = f"https://geocode.xyz/{latitude},{longitude}?json=1"
    geo_info = requests.request(url=url, method="GET", timeout=30)
    geo_info.raise_for_status()
    geo_json = geo_info.json()
    try:
        if "Throttled!" not in geo_json.values() and isinstance(geo_json, dict):
            city_info = {"state": geo_json["state"], "city": geo_json["city"]}
            return city_info
        else:
            return "Unknown"
    except (KeyError, TypeError):
        LOGGER.warning(
            f"Could not locate location info from Geocode. Response: {geo_json}"
        )
        return "Unknown"


def check_sor_field(model):
    """Check if the System of Record field is present and is set to "LibreNMS"."""
    return (
        "system_of_record" in model.custom_field_data
        and model.custom_field_data["system_of_record"] is not None
        and os.getenv("NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD", "LibreNMS") in model.custom_field_data["system_of_record"]
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
