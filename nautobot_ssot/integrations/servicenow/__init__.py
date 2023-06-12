"""Plugin declaration for nautobot_ssot_servicenow."""
from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.plugins import PluginConfig

from .signals import nautobot_database_ready_callback

try:
    from importlib import metadata
except ImportError:
    # Running on pre-3.8 Python; use importlib-metadata package
    import importlib_metadata as metadata

__version__ = metadata.version(__name__)


class NautobotSSOTServiceNowConfig(PluginConfig):
    """Plugin configuration for the nautobot_ssot_servicenow plugin."""

    name = "nautobot_ssot_servicenow"
    verbose_name = "Nautobot SSoT ServiceNow"
    version = __version__
    author = "Network to Code, LLC"
    description = "Nautobot SSoT ServiceNow."
    base_url = "ssot-servicenow"
    required_settings = []
    min_version = "1.4.0"
    max_version = "1.9999"
    default_settings = {}
    required_settings = []
    caching_config = {}

    home_view_name = "plugins:nautobot_ssot:dashboard"  # a link to the ServiceNow job would be even better
    config_view_name = "plugins:nautobot_ssot_servicenow:config"

    def ready(self):
        """Callback when this plugin is loaded."""
        super().ready()
        nautobot_database_ready.connect(nautobot_database_ready_callback, sender=self)


config = NautobotSSOTServiceNowConfig  # pylint:disable=invalid-name
