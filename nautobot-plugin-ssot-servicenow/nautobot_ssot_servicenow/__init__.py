"""Plugin declaration for nautobot_ssot_servicenow."""

__version__ = "0.1.0"

from nautobot.extras.plugins import PluginConfig


class NautobotSSOTServicenowConfig(PluginConfig):
    """Plugin configuration for the nautobot_ssot_servicenow plugin."""

    name = "nautobot_ssot_servicenow"
    verbose_name = "Nautobot SSoT ServiceNow"
    version = __version__
    author = "Network to Code, LLC"
    description = "Nautobot SSoT ServiceNow."
    base_url = "ssot-servicenow"
    required_settings = []
    min_version = "1.0.0"
    max_version = "1.9999"
    default_settings = {}
    caching_config = {}


config = NautobotSSOTServicenowConfig  # pylint:disable=invalid-name
