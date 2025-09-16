"""App declaration for nautobot_ssot."""

# Metadata is inherited from Nautobot. If not including Nautobot in the environment, this should be added
from importlib import metadata

from nautobot.apps import NautobotAppConfig

__version__ = metadata.version(__name__)


class NautobotSSOTAppConfig(NautobotAppConfig):
    """App configuration for the nautobot_ssot app."""

    name = "nautobot_ssot"
    verbose_name = "Single Source of Truth"
    version = __version__
    author = "Network to Code, LLC"
    description = "Nautobot Single Source of Truth."
    base_url = "ssot"
    required_settings = []
    default_settings = {}
    caching_config = {}
    docs_view_name = "plugins:nautobot_ssot:docs"
    searchable_models = ["sync"]


config = NautobotSSOTAppConfig  # pylint:disable=invalid-name
