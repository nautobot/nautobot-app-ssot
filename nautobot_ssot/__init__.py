"""Plugin declaration for nautobot_ssot."""

__version__ = "0.1.0"

from nautobot.extras.plugins import PluginConfig


class NautobotSSOTPluginConfig(PluginConfig):
    """Plugin configuration for the nautobot_ssot plugin."""

    name = "nautobot_ssot"
    verbose_name = "Single Source of Truth"
    version = __version__
    author = "Network to Code, LLC"
    description = "Nautobot Single Source of Truth"
    base_url = "ssot"
    required_settings = []
    min_version = "1.0.3"
    max_version = "1.9999"
    default_settings = {}
    caching_config = {}


config = NautobotSSOTPluginConfig  # pylint:disable=invalid-name
