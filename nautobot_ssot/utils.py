"""Utility functions for Nautobot SSoT App."""

import logging

from nautobot.dcim.models import Controller, ControllerManagedDeviceGroup
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import CustomField, SecretsGroup

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


def create_or_update_custom_field(key, field_type, label):
    """Create or update a custom field object."""
    cf_dict = {
        "type": field_type,
        "key": key,
        "label": label,
    }
    return CustomField.objects.update_or_create(key=cf_dict["key"], defaults=cf_dict)
