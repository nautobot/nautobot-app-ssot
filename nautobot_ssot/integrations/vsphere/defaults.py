"""Default settings to use across different files."""

from django.conf import settings

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})
DEFAULT_VSPHERE_TYPE = CONFIG.get("vsphere_type", "VMWare vSphere")
DEFAULT_CLUSTER_NAME = CONFIG.get("default_cluster_name", "vSphere Default Cluster")
