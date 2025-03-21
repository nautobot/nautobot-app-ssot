"""Default settings to use across different files."""

from django.conf import settings

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})


DEFAULT_LOCATION = CONFIG.get("cradlepoint_default_location_name")
DEFAULT_MANUFACTURER = CONFIG.get("cradlepoint_default_manufacturer_name")
DEFAULT_API_DEVICE_LIMIT = CONFIG.get("cradlepoint_default_api_limit")
