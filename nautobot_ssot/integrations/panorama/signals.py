# pylint: disable=invalid-name
"""Nautobot signal handler functions for panorama_sync."""

from django.apps import apps as global_apps
from django.conf import settings
from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import MetadataTypeDataTypeChoices

from nautobot_ssot.integrations.panorama.constants import (
    DEFAULT_FIREWALL_ROLE_NAME,
    FIREWALL_MANUFACTURER_NAME,
    FIREWALL_NETWORK_DRIVER,
)


def register_signals(sender):
    """Register signals for Panorama integration."""
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)


def nautobot_database_ready_callback(apps=global_apps, **kwargs):  # pylint: disable=too-many-locals
    """
    Sets up required database objects for the Panorama SSoT integration when Nautobot's database is ready.

    This function initializes and configures all necessary database objects required for integration
    between Nautobot and Palo Alto Networks Panorama, including:
    - Manufacturer for Palo Alto devices
    - Device roles and content types for Panorama controllers
    - Platform for PANOS
    - Metadata types and choices for tracking device controllers and sync status
    - Custom fields for application objects and address groups
    - Relationships between application objects
    Args:
        apps (django.apps.registry.Apps, optional): Django application registry.
            Defaults to global_apps.
        **kwargs: Additional keyword arguments passed by the signal dispatcher.

    Returns:
        None
    """
    # Get model Classes
    ContentType = apps.get_model("contenttypes", "ContentType")
    MetadataType = apps.get_model("extras", "MetadataType")

    Device = apps.get_model("dcim", "Device")
    Role = apps.get_model("extras", "Role")
    Manufacturer = apps.get_model("dcim", "Manufacturer")
    Controller = apps.get_model("dcim", "Controller")
    Platform = apps.get_model("dcim", "Platform")

    manufacturer, _ = Manufacturer.objects.get_or_create(name=FIREWALL_MANUFACTURER_NAME)

    device_content_type = ContentType.objects.get_for_model(Device)
    controller_content_type = ContentType.objects.get_for_model(Controller)
    role_name = settings.PLUGINS_CONFIG["nautobot_ssot"].get("panorama_firewall_role_name", DEFAULT_FIREWALL_ROLE_NAME)
    panorama_device_role, _ = Role.objects.get_or_create(name=role_name)
    panorama_device_role.content_types.add(device_content_type)
    panorama_device_role.content_types.add(controller_content_type)

    if not Platform.objects.filter(network_driver=FIREWALL_NETWORK_DRIVER).exists():
        Platform.objects.create(
            name=FIREWALL_NETWORK_DRIVER,
            network_driver=FIREWALL_NETWORK_DRIVER,
            manufacturer=manufacturer,
        )

    # Setup Metadata Objects
    ################
    # UPDATE THE BELOW TO USE METADATA UTILS ####
    #################
    last_sync_datetime, _ = MetadataType.objects.get_or_create(
        name="Last Panorama Sync",
        defaults={
            "description": "Date and time of the most recent sync with Panorama.",
            "data_type": MetadataTypeDataTypeChoices.TYPE_DATETIME,
        },
    )
    last_sync_datetime.content_types.add(ContentType.objects.get_for_model(Device))
