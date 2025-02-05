"""App declaration for nautobot_ssot_uisp."""

# Metadata is inherited from Nautobot. If not including Nautobot in the environment, this should be added
from importlib import metadata

from nautobot.apps import NautobotAppConfig

__version__ = metadata.version(__name__)


class NautobotSsotUispConfig(NautobotAppConfig):
    """App configuration for the nautobot_ssot_uisp app."""

    name = "nautobot_ssot_uisp"
    verbose_name = "Nautobot Ssot Uisp"
    version = __version__
    author = "Network to Code, LLC"
    description = "Nautobot Ssot Uisp."
    base_url = "ssot-uisp"
    required_settings = []
    min_version = "2.0.0"
    max_version = "2.9999"
    default_settings = {}
    caching_config = {}
    docs_view_name = "plugins:nautobot_ssot_uisp:docs"


config = NautobotSsotUispConfig  # pylint:disable=invalid-name
