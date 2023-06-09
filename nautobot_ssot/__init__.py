"""Plugin declaration for nautobot_ssot."""
# Metadata is inherited from Nautobot. If not including Nautobot in the environment, this should be added

try:
    from importlib import metadata
except ImportError:
    # Python version < 3.8
    import importlib_metadata as metadata

from nautobot.extras.plugins import PluginConfig

from nautobot_ssot.integrations.utils import each_enabled_integration_module
from nautobot_ssot.utils import logger

__version__ = metadata.version(__name__)


class NautobotSSOTPluginConfig(PluginConfig):
    """Plugin configuration for the nautobot_ssot plugin."""

    name = "nautobot_ssot"
    verbose_name = "Single Source of Truth"
    version = __version__
    author = "Network to Code, LLC"
    description = "Nautobot App that enables Single Source of Truth.  Allows users to aggregate distributed data sources and/or distribute Nautobot data to other data sources such as databases and SDN controllers."
    base_url = "ssot"
    required_settings = []
    min_version = "1.4.0"
    max_version = "1.9999"
    default_settings = {
        "enable_infoblox": False,
        "enable_ipfabric": False,
        "hide_example_jobs": True,
        "infoblox_default_status": "",
        "infoblox_enable_rfc1918_network_containers": False,
        "infoblox_enable_sync_to_infoblox": False,
        "infoblox_import_objects_ip_addresses": False,
        "infoblox_import_objects_subnets": False,
        "infoblox_import_objects_vlan_views": False,
        "infoblox_import_objects_vlans": False,
        "infoblox_import_subnets": [],
        "infoblox_password": "",
        "infoblox_url": "",
        "infoblox_username": "",
        "infoblox_verify_ssl": True,
        "infoblox_wapi_version": "",
        "ipfabric_api_token": "",
        "ipfabric_host": "",
        "ipfabric_ssl_verify": True,
        "ipfabric_timeout": 15,
        "nautobot_host": "",
    }
    caching_config = {}

    def ready(self):
        """Trigger callback when database is ready."""
        super().ready()

        for module in each_enabled_integration_module("signals"):
            logger.debug("Registering signals for %s", module.__file__)
            module.register_signals(self)


config = NautobotSSOTPluginConfig  # pylint:disable=invalid-name
