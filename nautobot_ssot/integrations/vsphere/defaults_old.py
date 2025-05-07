"""Default settings to use across different files."""

from django.conf import settings

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})
DEFAULT_CLUSTERGROUP_NAME = CONFIG.get("clustergroup_name", "vSphere Default Cluster Group")
DEFAULT_VSPHERE_TYPE_ = CONFIG.get("cluster_type", "VMWare vSphere")
DEFAULT_CLUSTER_NAME = CONFIG.get("cluster_name", "vSphere Default Cluster")
DEFAULT_TAG_COLOR = CONFIG.get("tag_color", "404dbf")
