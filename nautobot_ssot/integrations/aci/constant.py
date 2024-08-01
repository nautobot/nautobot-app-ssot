"""Constants for use with the ACI SSoT app."""

from django.conf import settings

try:
    from aci_models.models import (
        ApplicationProfile,
        BridgeDomain,
        EPG,
        ApplicationTermination,
    )

    HAS_ACI_MODELS = True
except ImportError:
    HAS_ACI_MODELS = False


def _read_settings() -> dict:
    config = settings.PLUGINS_CONFIG["nautobot_ssot"]
    return {key[4:]: value for key, value in config.items() if key.startswith("aci_")}


# Import config vars from nautobot_config.py
PLUGIN_CFG = _read_settings()
