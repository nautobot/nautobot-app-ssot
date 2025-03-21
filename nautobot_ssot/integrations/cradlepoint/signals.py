# pylint: disable=too-many-locals
# pylint: disable=duplicate-code
# pylint: disable=invalid-name

"""Signal handlers for nautobot_ssot_vsphere."""

from django.conf import settings
from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import (
    CustomFieldTypeChoices,
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)

config = settings.PLUGINS_CONFIG["nautobot_ssot"]


def register_signals(sender):
    """Register signals for Cradlepoint integration."""
    nautobot_database_ready.connect(create_default_cradlepoint_config, sender=sender)
    nautobot_database_ready.connect(
        create_default_cradlepoint_manufacturer, sender=sender
    )
    # nautobot_database_ready.connect(create_default_location, sender=sender)
    nautobot_database_ready.connect(create_default_custom_fields, sender=sender)


def create_default_cradlepoint_config(
    sender, *, apps, **kwargs
):  # pylint: disable=unused-argument
    """Create default Cradlepoint config."""
    SSOTCradlepointConfig = apps.get_model("nautobot_ssot", "SSOTCradlepointConfig")
    ExternalIntegration = apps.get_model("extras", "ExternalIntegration")
    Secret = apps.get_model("extras", "Secret")
    SecretsGroup = apps.get_model("extras", "SecretsGroup")
    SecretsGroupAssociation = apps.get_model("extras", "SecretsGroupAssociation")

    secrets_group, _ = SecretsGroup.objects.get_or_create(
        name="CradlepointSSOTDefaultSecretGroup"
    )
    cradlepoint_x_ecm_api_id, _ = Secret.objects.get_or_create(
        name="X-ECM-API-ID - Default",
        defaults={
            "provider": "environment-variable",
            "parameters": {"variable": "NAUTOBOT_SSOT_CRADLEPOINT_X_ECM_API_ID"},
        },
    )

    cradlepoint_x_ecm_api_key, _ = Secret.objects.get_or_create(
        name="X-ECM-API-KEY - Default",
        defaults={
            "provider": "environment-variable",
            "parameters": {"variable": "NAUTOBOT_SSOT_CRADLEPOINT_X_ECM_API_KEY"},
        },
    )

    cradlepoint_x_cp_api_id, _ = Secret.objects.get_or_create(
        name="X-CP-API-ID - Default",
        defaults={
            "provider": "environment-variable",
            "parameters": {"variable": "NAUTOBOT_SSOT_CRADLEPOINT_X_CP_API_ID"},
        },
    )

    cradlepoint_x_cp_api_key, _ = Secret.objects.get_or_create(
        name="X-CP-API-KEY - Default",
        defaults={
            "provider": "environment-variable",
            "parameters": {"variable": "NAUTOBOT_SSOT_CRADLEPOINT_X_CP_API_KEY"},
        },
    )

    SecretsGroupAssociation.objects.get_or_create(
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
        defaults={"secret": cradlepoint_x_ecm_api_id},
    )

    SecretsGroupAssociation.objects.get_or_create(
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
        defaults={"secret": cradlepoint_x_ecm_api_key},
    )

    SecretsGroupAssociation.objects.get_or_create(
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_SECRET,
        defaults={"secret": cradlepoint_x_cp_api_id},
    )

    SecretsGroupAssociation.objects.get_or_create(
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
        defaults={"secret": cradlepoint_x_cp_api_key},
    )

    external_integration, _ = ExternalIntegration.objects.get_or_create(
        name="DefaultCradlepointInstance",
        defaults={
            "remote_url": str(
                config.get("cradlepoint_url", "https://www.cradlepointecm.com")
            ),
            "secrets_group": secrets_group,
            "verify_ssl": bool(config.get("verify_ssl", False)),
            "timeout": 10,
        },
    )

    if not SSOTCradlepointConfig.objects.exists():
        SSOTCradlepointConfig.objects.create(
            name="CradlepointConfigDefault",
            description="Auto-generated default configuration.",
            cradlepoint_instance=external_integration,
            job_enabled=True,
        )


def create_default_cradlepoint_manufacturer(
    sender, *, apps, **kwargs
):  # pylint: disable=unused-argument
    """Create default Cradlepoint manufacturer."""
    Manufacturer = apps.get_model("dcim", "Manufacturer")
    default_manufacturer = config.get("cradlepoint_default_manufacturer_name")
    Manufacturer.objects.get_or_create(
        name=default_manufacturer,
    )


# def create_default_location(
#     sender, *, apps, **kwargs
# ):  # pylint: disable=unused-argument
#     """Create default location."""
#     default_location_name = config.get("cradlepoint_default_location_name")
#     default_location_type = config.get("cradlepoint_default_location_type")
#     default_parent_location_name = config.get(
#         "cradlepoint_default_parent_location_name"
#     )
#     default_parent_location_type = config.get(
#         "cradlepoint_default_parent_location_type"
#     )

#     Location = apps.get_model("dcim", "Location")
#     LocationType = apps.get_model("dcim", "LocationType")
#     Device = apps.get_model("dcim", "Device")
#     Status = apps.get_model("extras", "Status")
#     ContentType = apps.get_model("contenttypes", "ContentType")
#     location_type, _ = LocationType.objects.get_or_create(name=default_location_type)
#     location_type.content_types.set([ContentType.objects.get_for_model(Device)])
#     location_info = {
#         "name": default_location_name,
#         "location_type": location_type,
#         "status": Status.objects.get(name="Active"),
#     }
#     if default_parent_location_name:
#         location_info["parent"] = Location.objects.get_or_create(
#             name=default_parent_location_name,
#             location_type__name=default_parent_location_type,
#         )

#     Location.objects.get_or_create(
#         **location_info,
#     )


def create_default_custom_fields(
    sender, *, apps, **kwargs
):  # pylint: disable=unused-argument
    """Create default Custom Fields."""
    CustomField = apps.get_model("extras", "CustomField")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Device = apps.get_model("dcim", "Device")

    device_lat, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_TEXT,
        key="device_latitude",
        label="Device Latitude",
    )
    device_lat.content_types.add(ContentType.objects.get_for_model(Device))

    device_lon, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_TEXT,
        key="device_longitude",
        label="Device Longitude",
    )
    device_lon.content_types.add(ContentType.objects.get_for_model(Device))

    device_alt, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_TEXT,
        key="device_altitude",
        label="Device Altitude",
    )
    device_alt.content_types.add(ContentType.objects.get_for_model(Device))

    device_accuracy, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_INTEGER,
        key="device_accuracy",
        label="Device Accuracy",
    )
    device_accuracy.content_types.add(ContentType.objects.get_for_model(Device))

    device_gps_method, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_TEXT,
        key="device_gps_method",
        label="Device GPS Method",
    )
    device_gps_method.content_types.add(ContentType.objects.get_for_model(Device))

    cradlepoint_id_number, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_TEXT,
        key="cradlepoint_id_number",
        label="Cradlepoint ID Number",
        advanced_ui=True,
    )
    cradlepoint_id_number.content_types.add(ContentType.objects.get_for_model(Device))
