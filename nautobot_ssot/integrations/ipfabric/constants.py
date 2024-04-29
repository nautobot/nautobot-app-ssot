"""Constants used by IPFabric Integration."""

from django.conf import settings

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})

# Required Settings
IPFABRIC_HOST = CONFIG.get("ipfabric_host")
IPFABRIC_API_TOKEN = CONFIG.get("ipfabric_api_token")
IPFABRIC_SSL_VERIFY = CONFIG.get("ipfabric_ssl_verify")
NAUTOBOT_HOST = CONFIG.get("nautobot_host")
# Optional Settings
IPFABRIC_TIMEOUT = int(CONFIG.get("ipfabric_timeout", 15))
ALLOW_DUPLICATE_ADDRESSES = CONFIG.get("ipfabric_allow_duplicate_addresses", True)
DEFAULT_DEVICE_ROLE = CONFIG.get("ipfabric_default_device_role", "Network Device")
DEFAULT_DEVICE_ROLE_COLOR = CONFIG.get("ipfabric_default_device_role_color", "ff0000")
DEFAULT_DEVICE_STATUS = CONFIG.get("ipfabric_default_device_status", "Active")
DEFAULT_DEVICE_STATUS_COLOR = CONFIG.get("ipfabric_default_device_status_color", "ff0000")
DEFAULT_INTERFACE_MAC = CONFIG.get("ipfabric_default_interface_mac", "00:00:00:00:00:01")
DEFAULT_INTERFACE_MTU = int(CONFIG.get("ipfabric_default_interface_mtu", 1500))
DEFAULT_INTERFACE_TYPE = CONFIG.get("ipfabric_default_interface_type", "1000base-t")
SAFE_DELETE_DEVICE_STATUS = CONFIG.get("ipfabric_safe_delete_device_status", "Offline")
SAFE_DELETE_LOCATION_STATUS = CONFIG.get("ipfabric_safe_delete_location_status", "Decommissioning")
SAFE_DELETE_VLAN_STATUS = CONFIG.get("ipfabric_safe_delete_vlan_status", "Deprecated")
SAFE_DELETE_IPADDRESS_STATUS = CONFIG.get("ipfabric_safe_delete_ipaddress_status", "Deprecated")
LAST_SYNCHRONIZED_CF_NAME = "last_synced_from_sor"
IP_FABRIC_USE_CANONICAL_INTERFACE_NAME = CONFIG.get("ipfabric_use_canonical_interface_name", False)
