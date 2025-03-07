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


def create_default_cradlepoint_config(
    sender, *, apps, **kwargs
):  # pylint: disable=unused-argument
    """Create default Cradlepoint config."""
    SSOTCradlepointConfig = apps.get_model("nautobot_ssot", "SSOTCradlepointConfig")
    ExternalIntegration = apps.get_model("extras", "ExternalIntegration")
    Secret = apps.get_model("extras", "Secret")
    SecretsGroup = apps.get_model("extras", "SecretsGroup")
    SecretsGroupAssociation = apps.get_model("extras", "SecretsGroupAssociation")
    ContentType = apps.get_model("contenttypes", "ContentType")

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
        secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
        defaults={"secret": cradlepoint_x_ecm_api_id},
    )

    SecretsGroupAssociation.objects.get_or_create(
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
        defaults={"secret": cradlepoint_x_ecm_api_key},
    )

    SecretsGroupAssociation.objects.get_or_create(
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
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


def create_default_cradlepoint_manufacturer(sender, *, apps, **kwargs):
    """Create default Cradlepoint manufacturer."""
    Manufacturer = apps.get_model("dcim", "Manufacturer")
    Manufacturer.objects.get_or_create(
        name="Cradlepoint Inc.",
    )
