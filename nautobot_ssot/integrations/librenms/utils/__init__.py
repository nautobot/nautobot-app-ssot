"""Utility functions for working with LibreNMS and Nautobot."""

import inspect
import ipaddress
import logging
import os

from constance import config as constance_name
from django.conf import settings
from django.core.exceptions import ValidationError

from nautobot.dcim.models.locations import Location, LocationType
from nautobot.dcim.models.devices import DeviceType, Manufacturer, Platform
from nautobot.extras.models.roles import Role
from nautobot_ssot.integrations.librenms.constants import os_manufacturer_map, PLUGIN_CFG


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
    try:
        hostname = ipaddress.IPv4Address(device[job.hostname_field])
    except ipaddress.AddressValueError:
        try:
            hostname = ipaddress.IPv6Address(device[job.hostname_field])
        except ipaddress.AddressValueError:
            hostname = device[job.hostname_field].split(".")[0].upper()
    if isinstance(hostname, ipaddress.IPv4Address) or isinstance(hostname, ipaddress.IPv6Address):
        if not settings.PLUGINS_CONFIG["nautobot_ssot"]["librenms_allow_ip_hostnames"]:
            job.logger.error(f"The hostname {device[job.hostname_field]} cannot be an IP Address")
            device["load_errors"].append("The hostname cannot be an IP Address")
            return False
    return str(hostname)


def has_valid_location_data(device, location_type):
    """Validate location data fields."""
    if location_type is not None and device["location"] is not None:
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


def has_valid_device_id(device):
    """Check if the device has a device_id."""
    if isinstance(device["device_id"], int):
        return True
    else:
        device["load_errors"].append("Device ID is required")
        return False


def has_valid_role(device, job):
    """Check if the device has a device type for the role field."""
    if isinstance(device["type"], str):
        try:
            Role.objects.get(name=device["type"])
            return True
        except Role.DoesNotExist as err:
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
    else:
        device["load_errors"].append("Device Type is required")
        return False


def has_valid_manufacturer_data(device, job):
    """Check if the device has a valid manufacturer."""
    if isinstance(device["os"], str):
        if os_manufacturer_map.get(device["os"]):
            try:
                Manufacturer.objects.get(name=os_manufacturer_map.get(device["os"]))
                return True
            except Manufacturer.DoesNotExist as err:
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
        else:
            device["load_errors"].append("Manufacturer is unknown")
            return False
    else:
        device["load_errors"].append("Manufacturer is required")
        return False
    

def has_valid_device_type(device, job):
    """Check if the device has a valid device type for the hardware field."""
    if isinstance(device["hardware"], str):
        try:
            DeviceType.objects.get(model=device["hardware"])
            return True
        except DeviceType.DoesNotExist as err:
            if has_valid_manufacturer_data(device, job):
                job.logger.info(f"Creating device type {device['hardware']}")
                _manufacturer = Manufacturer.objects.get(name=os_manufacturer_map.get(device["os"]))
                try:
                    _device_type = DeviceType.objects.create(model=device["hardware"], manufacturer=_manufacturer)
                    _device_type.validated_save()
                    return True
                except ValidationError as err:
                    reason = err.args[0]
                    device["load_errors"].append(reason)
                    return False
            else:
                reason = err.args[0]
        except DeviceType.MultipleObjectsReturned as err:
            reason = err.args[0]
        device["load_errors"].append(reason)
        return False
    else:
        device["load_errors"].append("Device Type is required")
        return False


def has_valid_platform(device, job):
    """Check if the device has a valid platform."""
    if isinstance(device["os"], str):
        try:
            Platform.objects.get(name=device["os"])
            return True
        except Platform.DoesNotExist as err:
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
    else:
        device["load_errors"].append("Platform is required")
        return False
    

def validate_device_data(device, job):
    """Validate device data fields."""
    device["load_errors"] = []
    validated_device = {}
    validated_device["name"] = normalize_device_hostname(device, job)
    validated_device["device_id"] = has_valid_device_id(device)
    validated_device["location"] = has_valid_location_data(device, job.location_type)
    validated_device["role"] = has_valid_role(device, job)
    validated_device["manufacturer"] = has_valid_manufacturer_data(device, job)
    validated_device["device_type"] = has_valid_device_type(device, job)
    validated_device["platform"] = has_valid_platform(device, job)
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
