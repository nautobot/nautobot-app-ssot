"""Utility/helper functions for nautobot-ssot-servicenow."""

import logging

from django.conf import settings

from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices

from .models import SSOTServiceNowConfig


logger = logging.getLogger(__name__)


def get_servicenow_parameters():
    """Get a dictionary containing the instance, username, and password for connecting to ServiceNow."""
    db_config = SSOTServiceNowConfig.load()
    settings_config = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})
    result = {
        "instance": settings_config.get("servicenow_instance", db_config.servicenow_instance),
        "username": settings_config.get("servicenow_username", ""),
        "password": settings_config.get("servicenow_password", ""),
    }
    if not result["username"]:
        try:
            result["username"] = db_config.servicenow_secrets.get_secret_value(
                SecretsGroupAccessTypeChoices.TYPE_REST,
                SecretsGroupSecretTypeChoices.TYPE_USERNAME,
                obj=db_config,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Unable to retrieve ServiceNow username: %s", exc)
    if not result["password"]:
        try:
            result["password"] = db_config.servicenow_secrets.get_secret_value(
                SecretsGroupAccessTypeChoices.TYPE_REST,
                SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
                obj=db_config,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Unable to retrieve ServiceNow username: %s", exc)
    return result
