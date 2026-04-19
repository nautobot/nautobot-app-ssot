# pylint: disable=invalid-name
"""Nautobot signal handler functions for panorama_sync."""

from django.apps import apps as global_apps
from django.conf import settings
from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import MetadataTypeDataTypeChoices


def register_signals(sender):
    """Register signals for LibreNMS integration."""
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
    app_settings = settings.PLUGINS_CONFIG.get("nautobot_ssot")
    # Get model Classes
    ContentType = apps.get_model("contenttypes", "ContentType")
    MetadataType = apps.get_model("extras", "MetadataType")

    Device = apps.get_model("dcim", "Device")
    Role = apps.get_model("extras", "Role")
    Manufacturer = apps.get_model("dcim", "Manufacturer")
    Platform = apps.get_model("dcim", "Platform")
    Controller = apps.get_model("dcim", "Controller")
    manufacturer_name = app_settings.get("panorama_firewall_manufacturer_name", "Palo Alto")
    manufacturer, _ = Manufacturer.objects.get_or_create(name=manufacturer_name)

    device_content_type = ContentType.objects.get_for_model(Device)
    controller_content_type = ContentType.objects.get_for_model(Controller)
    role_name = app_settings.get("panorama_firewall_role_name", "Firewall")
    panorama_device_role, _ = Role.objects.get_or_create(name=role_name)
    panorama_device_role.content_types.add(device_content_type)
    panorama_device_role.content_types.add(controller_content_type)

    platform_name = app_settings.get("panorama_firewall_platform_name", "paloalto_panos")
    Platform.objects.get_or_create(name=platform_name, manufacturer=manufacturer)

    # Setup Metadata Objects
    ################
    # UPDATE THE BELOW TO USE METADATA UTILS ####
    #################
    last_sync_datetime, _ = MetadataType.objects.get_or_create(
        name="Last Panorama Sync",
        description="Date and time of the most recent sync with Panorama.",
        data_type=MetadataTypeDataTypeChoices.TYPE_DATETIME,
    )
    last_sync_datetime.content_types.add(ContentType.objects.get_for_model(Device))
