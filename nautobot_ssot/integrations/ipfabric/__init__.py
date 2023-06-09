"""Plugin declaration for nautobot_ssot_ipfabric."""
# Metadata is inherited from Nautobot. If not including Nautobot in the environment, this should be added
try:
    from importlib import metadata
except ImportError:
    # Python version < 3.8
    import importlib_metadata as metadata

__version__ = metadata.version(__name__)

from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.plugins import PluginConfig

from nautobot_ssot_ipfabric.signals import nautobot_database_ready_callback


class NautobotSSoTIPFabricConfig(PluginConfig):
    """Plugin configuration for the nautobot_ssot_ipfabric plugin."""

    name = "nautobot_ssot_ipfabric"
    verbose_name = "Nautobot SSoT IPFabric"
    version = __version__
    author = "Network to Code, LLC"
    description = "Nautobot SSoT IPFabric."
    base_url = "ssot-ipfabric"
    required_settings = ["ipfabric_host", "ipfabric_api_token"]
    min_version = "1.2.0"
    max_version = "1.9999"
    default_settings = {
        "ipfabric_ssl_verify": False,
        "ipfabric_timeout": 15,
    }
    caching_config = {}

    def ready(self):
        """Callback when this plugin is loaded."""
        super().ready()
        nautobot_database_ready.connect(nautobot_database_ready_callback, sender=self)


config = NautobotSSoTIPFabricConfig  # pylint:disable=invalid-name
