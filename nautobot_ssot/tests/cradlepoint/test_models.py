"""Cradlepoint models tests."""
import os
from copy import deepcopy
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase
from nautobot.extras.choices import (
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)
from nautobot.extras.models import (
    ExternalIntegration,
    Secret,
    SecretsGroup,
    SecretsGroupAssociation,
    Status,
)

from nautobot_ssot.integrations.cradlepoint.models import SSOTCradlepointConfig


@mock.patch.dict(
    os.environ,
    {
        "NAUTOBOT_SSOT_CRADLEPOINT_X_ECM_API_ID": "1234",
        "NAUTOBOT_SSOT_CRADLEPOINT_X_ECM_API_KEY": "12345",
        "NAUTOBOT_SSOT_CRADLEPOINT_X_CP_API_ID": "123456,",
        "NAUTOBOT_SSOT_CRADLEPOINT_X_CP_API_KEY": "1234567",
    },
)
class SSOTCradlepointConfigTestCase(TestCase):
    """Tests for SSOTCradlepointConfig model."""

    def setUp(self):
        """Set up the test."""
        secrets_group, _ = SecretsGroup.objects.get_or_create(
            name="CradlepointSSOTUnitTest"
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
                "remote_url": "https://www.cradlepointecm.com",
                "secrets_group": secrets_group,
                "verify_ssl": bool(config.get("verify_ssl", False)),
                "timeout": 10,
            },
        )
