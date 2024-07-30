"""Plugin declaration for bootstrap."""
# Metadata is inherited from Nautobot. If not including Nautobot in the environment, this should be added
try:
    from importlib import metadata
except ImportError:
    # Python version < 3.8
    import importlib_metadata as metadata

__version__ = metadata.version(__name__)

from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.plugins import NautobotAppConfig
from nautobot_ssot.integrations.bootstrap.signals import nautobot_database_ready_callback

__version__ = metadata.version(__name__)


class NautobotSsotBootstrapConfig(NautobotAppConfig):
    """Plugin configuration for the Bootstrap App."""

    name = "nautobot_ssot_bootstrap"
    verbose_name = "Nautobot SSoT Bootstrap"
    version = __version__
    author = "Network to Code, LLC"
    description = "Nautobot SSoT Bootstrap."
    base_url = "ssot-bootstrap"
    has_sensitive_variables = False
    required_settings = []
    min_version = "2.0.0"
    max_version = "2.9999"
    default_settings = {}
    caching_config = {}

    def ready(self):
        """Trigger callback when database is ready."""
        super().ready()

        nautobot_database_ready.connect(nautobot_database_ready_callback, sender=self)


config = NautobotSsotBootstrapConfig  # pylint:disable=invalid-name
