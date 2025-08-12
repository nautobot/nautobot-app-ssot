"""Utility functions for Nautobot SSoT App."""

import json
import logging
import re
from importlib.metadata import PackageNotFoundError, version
from typing import List, Tuple

from nautobot.dcim.models import Controller, ControllerManagedDeviceGroup
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import SecretsGroup

logger = logging.getLogger("nautobot.ssot")


def get_username_password_https_from_secretsgroup(group: SecretsGroup):
    """Retrieve username and password from a HTTPS SecretsGroup.

    Args:
        group (SecretsGroup): The SecretsGroup containing HTTPS access-types.
    """
    username = group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
    )
    password = group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
    )
    return username, password


def verify_controller_managed_device_group(controller: Controller) -> ControllerManagedDeviceGroup:
    """Validate that Controller Managed Device Group exists or create it.

    Args:
        controller (Controller): Controller for associated ManagedDeviceGroup.

    Returns:
        ControllerManagedDeviceGroup: The ControllerManagedDeviceGroup that was either found or created for the Controller.
    """
    return ControllerManagedDeviceGroup.objects.get_or_create(
        controller=controller, defaults={"name": f"{controller.name} Managed Devices"}
    )[0]


def create_or_update_custom_field(apps, key, field_type, label):
    """Create or update a custom field object."""
    CustomField = apps.get_model("extras", "CustomField")  # pylint: disable=invalid-name
    cf_dict = {
        "type": field_type,
        "key": key,
        "label": label,
    }
    return CustomField.objects.update_or_create(key=cf_dict["key"], defaults=cf_dict)


def parse_hostname_for_location(
    location_map: dict[str, dict[str, str]], device_hostname: str, device_location: str
) -> dict:
    """Parse device hostname from location_map to get Device Location.

    Args:
        location_map (dict[str, dict[str, str]]): Dictionary of locations.
        device_hostname (str): Hostname of Device to determine location of.

    Returns:
        dict: Dictionary of DeviceLocation data. Includes location name and parent location name.
    """
    # Handle case where location_map might be a JSON string
    if isinstance(location_map, str):
        try:
            location_map = json.loads(location_map)
        except (json.JSONDecodeError, TypeError):
            # If it's not valid JSON, treat as empty
            location_map = None

    # Early return if no location_map provided or after JSON parsing failed
    if not location_map:
        return {
            "name": device_location,
            "parent": None,
        }

    # Handle dictionary format where key is pattern and value contains Name/Parent
    if isinstance(location_map, dict):
        for pattern, mapping in location_map.items():
            # Make pattern matching case-insensitive
            match = re.match(pattern=pattern, string=device_hostname, flags=re.IGNORECASE)
            if match:
                return {
                    "name": mapping.get("Name"),
                    "parent": mapping.get("Parent"),
                }

    # Handle list of mappings format (legacy format)
    if isinstance(location_map, list):
        for entry in location_map:
            if isinstance(entry, dict) and "prefix" in entry:
                # Use the prefix as the regex pattern
                pattern = entry["prefix"]
                match = re.match(pattern=pattern, string=device_hostname)
                if match:
                    return {
                        "name": entry["location"],
                        "parent": entry.get("parent", None),
                    }

    # If no match found in location_map, fall back to device_location
    return {
        "name": device_location,
        "parent": None,
    }


def parse_hostname_for_role(hostname_map: List[Tuple[str, str]], device_hostname: str, default_role: str):
    """Parse device hostname from hostname_map to get Device Role.

    Args:
        hostname_map (List[Tuple[str, str]]): List of tuples containing regex to compare with hostname and associated DeviceRole name.
        device_hostname (str): Hostname of Device to determine role of.
        default_role (str): String representing default Role to return if no match found.

    Returns:
        str: Name of DeviceRole. Defaults to default_role.
    """
    device_role = default_role

    # Handle case where hostname_map might be a JSON string
    if isinstance(hostname_map, str):
        try:
            hostname_map = json.loads(hostname_map)
        except (json.JSONDecodeError, TypeError):
            # If it's not valid JSON, treat as empty
            hostname_map = None

    if hostname_map:
        for entry in hostname_map:
            match = re.match(pattern=entry[0], string=device_hostname)
            if match:
                device_role = entry[1]
    return device_role


def validate_dlm_installed() -> bool:
    """Validate if the DLM App is installed.

    Returns:
        bool: True if DLM App is installed, False otherwise.
    """
    try:
        version("nautobot_device_lifecycle_mgmt")
        return True
    except PackageNotFoundError:
        pass
    return False
