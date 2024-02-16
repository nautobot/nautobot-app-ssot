"""Default settings to use across different files."""

from django.conf import settings

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})
DEFAULT_VSPHERE_TYPE = CONFIG.get("vsphere_type", "VMWare vSphere")
ENFORCE_CLUSTER_GROUP_TOP_LEVEL = CONFIG.get("enforce_cluster_group_top_level", True)
VSPHERE_USERNAME = CONFIG["vsphere_username"]
VSPHERE_PASSWORD = CONFIG["vsphere_password"]
VSPHERE_VERIFY_SSL = CONFIG.get("vsphere_verify_ssl", False)
VSPHERE_URI = CONFIG["vsphere_uri"]
DEFAULT_VM_STATUS_MAP = CONFIG.get(
    "vsphere_vm_status_map", {"POWERED_OFF": "Offline", "POWERED_ON": "Active", "SUSPENDED": "Suspended"}
)
DEFAULT_IP_STATUS_MAP = CONFIG.get("vsphere_ip_status_map", {"PREFERRED": "Active", "UNKNOWN": "Reserved"})
VSPHERE_VM_INTERFACE_MAP = CONFIG.get("vsphere_vm_interface_map", {"NOT_CONNECTED": False, "CONNECTED": True})
PRIMARY_IP_SORT_BY = CONFIG.get("primary_ip_sort_by", "Lowest")
DEFAULT_USE_CLUSTERS = CONFIG.get("default_use_clusters", True)
DEFAULT_CLUSTER_NAME = CONFIG.get("default_cluster_name", "vSphere Default Cluster")
DEFAULT_IGNORE_LINK_LOCAL = CONFIG.get("default_ignore_link_local", True)
DEFAULT_IGNORE_APIPA = CONFIG.get("default_ignore_apipa", True)
