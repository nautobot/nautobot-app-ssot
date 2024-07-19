"""Itential SSoT API Clients fixtures."""

import unittest

from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices

from nautobot_ssot.integrations.itential.models import AutomationGatewayModel
from nautobot_ssot.integrations.itential.clients import AutomationGatewayClient


def api_client(device_obj: AutomationGatewayModel, job: object = unittest.mock.MagicMock()) -> AutomationGatewayClient:
    """Initialize API Client."""

    return AutomationGatewayClient(
        host=device_obj.gateway.remote_url,
        username=device_obj.gateway.secrets_group.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_REST, secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME
        ),
        password=device_obj.gateway.secrets_group.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_REST, secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD
        ),
        job=job,
        verify_ssl=device_obj.gateway.verify_ssl,
    )
