"""Constants used by Slurpit Integration."""

from django.conf import settings

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})

# Required Settings
DEFAULT_DEVICE_ROLE = CONFIG.get("slurpit_default_device_role", "Network Device")
DEFAULT_DEVICE_ROLE_COLOR = CONFIG.get("slurpit_default_device_role_color", "ff0000")
DEFAULT_DEVICE_STATUS = CONFIG.get("slurpit_default_device_status", "Active")
DEFAULT_DEVICE_STATUS_COLOR = CONFIG.get("slurpit_default_device_status_color", "ff0000")
