"""Plugin declaration for nautobot_data_sync."""

__version__ = "0.1.0"

from nautobot.extras.plugins import PluginConfig


class NautobotDataSyncConfig(PluginConfig):
    """Plugin configuration for the nautobot_data_sync plugin."""

    name = "nautobot_data_sync"
    verbose_name = "Nautobot Data Sync"
    version = __version__
    author = "Network to Code, LLC"
    description = "Nautobot Data Sync"
    base_url = "data-sync"
    required_settings = []
    min_version = "1.0.1"
    max_version = "1.9999"
    default_settings = {}
    caching_config = {}


config = NautobotDataSyncConfig  # pylint:disable=invalid-name
