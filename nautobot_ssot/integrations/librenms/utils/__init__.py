"""Utility functions for working with LibreNMS and Nautobot."""

# pylint: disable=duplicate-code

import inspect
import ipaddress
import json
import logging
import os

from constance import config as constance_name
from django.conf import settings
from django.core.exceptions import ValidationError
from nautobot.dcim.models.devices import DeviceType, Manufacturer, Platform
from nautobot.dcim.models.locations import Location, LocationType
from nautobot.extras.models.roles import Role

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

    # try:
    #     hostname = ipaddress.ip_address(hostname_str)
    #     if not settings.PLUGINS_CONFIG["nautobot_ssot"]["librenms_allow_ip_hostnames"]:
    #         return {"valid": False, "reason": "The hostname cannot be an IP Address"}
    # except ValueError:
    hostname = hostname_str.split(".")[0].upper() if not hostname_is_ip_address(hostname_str) else hostname_str

    return str(hostname)


def hostname_is_ip_address(hostname_str):
    """Check if the hostname is a valid IP address."""
    try:
        ipaddress.ip_address(hostname_str)
        return True
    except ValueError:
        return False


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
    if unpermitted_values and hasattr(unpermitted_values, "__str__") and not isinstance(unpermitted_values, list):
        try:
            unpermitted_values = json.loads(str(unpermitted_values))
        except (json.JSONDecodeError, TypeError):
            # If it's not valid JSON, treat as None
            unpermitted_values = None

    for key in required_values_dict:  # pylint: disable=consider-using-dict-items
        if (
            key == job.hostname_field
            and hostname_is_ip_address(device.get(key))
            and not settings.PLUGINS_CONFIG["nautobot_ssot"]["librenms_allow_ip_hostnames"]
        ):
            required_values_dict[key]["valid"] = False
            required_values_dict[key]["reason"] = "The hostname cannot be an IP Address"
        if key in device and isinstance(device[key], dict) and device[key].get("reason"):
            required_values_dict[key] = device[key]
        if key not in device or not isinstance(device.get(key), str) or device.get(key) in [None, ""]:
            required_values_dict[key]["valid"] = False
            required_values_dict[key]["reason"] = "String is required"
        if unpermitted_values and device.get(key) in unpermitted_values:
            required_values_dict[key]["valid"] = False
            required_values_dict[key]["reason"] = f"{key} cannot be '{device[key]}'"
        if key == "platform" and required_values_dict[key]["valid"] and device.get(key) not in os_manufacturer_map:
            required_values_dict[key]["valid"] = False
            required_values_dict[key]["reason"] = f"Manufacturer mapping not found for OS: {device[key]}"

    return required_values_dict


def has_valid_location_data(device, location_type):
    """Validate location data fields."""
    try:
        _location_type = LocationType.objects.get(name=location_type)
        Location.objects.get(name=device["location"], location_type=_location_type)
        return True
    except LocationType.DoesNotExist as err:
        reason = err.args[0]
    except Location.DoesNotExist as err:
        reason = err.args[0] + " - Sync Locations from LibreNMS"
    except Location.MultipleObjectsReturned as err:
        reason = err.args[0]
    device["load_errors"].append(reason)
    return False


def has_valid_role(device, job):
    """Check if the device has a device type for the role field."""
    try:
        Role.objects.get(name=device["type"])
        return True
    except Role.DoesNotExist:
        job.logger.info(f"Creating role {device['type']}")
        try:
            _role = Role.objects.create(name=device["type"])
            _role.validated_save()
        except ValidationError as err:
            reason = err.args[0]
            device["load_errors"].append(reason)
            return False
        return True
    except Role.MultipleObjectsReturned as err:
        reason = err.args[0]
    device["load_errors"].append(reason)
    return False


def has_valid_manufacturer_data(device, job):
    """Check if the device has a valid manufacturer."""
    if os_manufacturer_map.get(device["os"]):
        try:
            Manufacturer.objects.get(name=os_manufacturer_map.get(device["os"]))
            return True
        except Manufacturer.DoesNotExist:
            job.logger.info(f"Creating manufacturer {os_manufacturer_map.get(device['os'])}")
            try:
                _manufacturer = Manufacturer.objects.create(name=os_manufacturer_map.get(device["os"]))
                _manufacturer.validated_save()
                return True
            except ValidationError as err:
                reason = err.args[0]
                device["load_errors"].append(reason)
                return False
        except Manufacturer.MultipleObjectsReturned as err:
            reason = err.args[0]
        device["load_errors"].append(reason)
        return False
    device["load_errors"].append("Manufacturer is unknown")
    return False


def has_valid_device_type(device, job):
    """Check if the device has a valid device type for the hardware field."""
    try:
        DeviceType.objects.get(model=device["hardware"])
        return True
    except DeviceType.DoesNotExist as does_not_exist_error:
        if has_valid_manufacturer_data(device, job):
            job.logger.info(f"Creating device type {device['hardware']}")
            _manufacturer = Manufacturer.objects.get(name=os_manufacturer_map.get(device["os"]))
            try:
                _device_type = DeviceType.objects.create(model=device["hardware"], manufacturer=_manufacturer)
                _device_type.validated_save()
                return True
            except ValidationError as validation_error:
                reason = validation_error.args[0]
                device["load_errors"].append(reason)
                return False
        reason = does_not_exist_error.args[0]
    except DeviceType.MultipleObjectsReturned as multiple_objects_error:
        reason = multiple_objects_error.args[0]
    device["load_errors"].append(reason)
    return False


def has_valid_platform(device, job):
    """Check if the device has a valid platform."""
    try:
        Platform.objects.get(name=device["os"])
        return True
    except Platform.DoesNotExist:
        job.logger.info(f"Creating platform {device['os']}")
        try:
            _platform = Platform.objects.create(name=device["os"])
            _platform.validated_save()
        except ValidationError as err:
            reason = err.args[0]
            device["load_errors"].append(reason)
            return False
        return True
    except Platform.MultipleObjectsReturned as err:
        reason = err.args[0]
    device["load_errors"].append(reason)
    return False


def validate_device_data(device, job):
    """Validate device data fields."""
    device["load_errors"] = []
    validated_device = {}
    if has_required_values(device, job):
        validated_device["name"] = normalize_device_hostname(device, job)
        validated_device["location"] = has_valid_location_data(device, job.location_type)
        validated_device["role"] = has_valid_role(device, job)
        validated_device["manufacturer"] = has_valid_manufacturer_data(device, job)
        validated_device["device_type"] = has_valid_device_type(device, job)
        validated_device["platform"] = has_valid_platform(device, job)
        validated_device["load_errors"] = list(set(device["load_errors"]))
        return validated_device
    validated_device["load_errors"] = list(set(device["load_errors"]))
    return validated_device


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
