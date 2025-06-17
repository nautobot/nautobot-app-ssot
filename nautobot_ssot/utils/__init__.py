"""Utility functions for Nautobot SSoT App."""

import logging
import re
from importlib.metadata import PackageNotFoundError, version
from typing import List, Tuple

from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import SecretsGroup

try:
    from nautobot.dcim.models import Controller, ControllerManagedDeviceGroup

    CONTROLLER_FOUND = True
except (ImportError, RuntimeError):
    CONTROLLER_FOUND = False


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


if CONTROLLER_FOUND:

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
    if hostname_map:  # pylint: disable=duplicate-code
        for entry in hostname_map:
            match = re.match(pattern=entry[0], string=device_hostname)
            if match:
                device_role = entry[1]
    return device_role


def dlm_supports_softwarelcm() -> bool:
    """Validate if the DLM version installed is 2.0.0 or lower.

    Returns:
        bool: True if DLM version is 2.0.0 or lower, False otherwise.
    """
    try:
        dlm_version = version("nautobot_device_lifecycle_mgmt")
        if re.match("[012].+", dlm_version):
            return True
    except PackageNotFoundError:
        pass
    return False


def core_supports_softwareversion() -> bool:
    """Validate if the core Nautobot version installed is 2.2.0 or higher.

    Returns:
        bool: True if Nautobot version is 2.2.0 or higher, False otherwise.
    """
    nb_version = version("nautobot")
    if re.match("2.[23456789].+", nb_version):
        return True
    return False


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
