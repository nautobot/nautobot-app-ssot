"""Default settings to use across different files."""

from django.conf import settings

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})


DEFAULT_LOCATION = CONFIG.get("cradlepoint_default_location_name")
DEFAULT_MANUFACTURER = "Cradlepoint Inc."
