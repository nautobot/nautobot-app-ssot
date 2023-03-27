"""Plugin declaration for nautobot_ssot."""
# Metadata is inherited from Nautobot. If not including Nautobot in the environment, this should be added
try:
    from importlib import metadata
except ImportError:
    # Python version < 3.8
    import importlib_metadata as metadata

__version__ = metadata.version(__name__)

from django.conf import settings
from nautobot.extras.plugins import PluginConfig


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
        "hide_example_jobs": False,
    }
    caching_config = {}

    def ready(self):
        """Register metric functions when plug-in ready."""
        super().ready()

        # App metrics are disabled by default
        if getattr(settings, "METRICS_ENABLED", False):
            # pylint: disable=import-outside-toplevel
            from nautobot_capacity_metrics import register_metric_func
            from nautobot_ssot.metrics import (
                metric_ssot_jobs,
                metric_syncs,
                metric_sync_operations,
                metric_memory_usage,
            )

            register_metric_func(metric_ssot_jobs)
            register_metric_func(metric_syncs)
            register_metric_func(metric_sync_operations)
            register_metric_func(metric_memory_usage)


config = NautobotSSOTPluginConfig  # pylint:disable=invalid-name
