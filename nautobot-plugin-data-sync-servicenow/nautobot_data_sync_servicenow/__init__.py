"""Plugin declaration for nautobot_data_sync_servicenow."""

__version__ = "0.1.0"

from nautobot.extras.plugins import PluginConfig


class NautobotDataSyncServicenowConfig(PluginConfig):
    """Plugin configuration for the nautobot_data_sync_servicenow plugin."""

    name = "nautobot_data_sync_servicenow"
    verbose_name = "Nautobot ServiceNow Data Synchronization"
    version = __version__
    author = "Network to Code, LLC"
    description = "Nautobot ServiceNow Data Synchronization."
    base_url = "data-sync-servicenow"
    required_settings = []
    min_version = "1.0.0"
    max_version = "1.9999"
    default_settings = {}
    caching_config = {}


config = NautobotDataSyncServicenowConfig  # pylint:disable=invalid-name
