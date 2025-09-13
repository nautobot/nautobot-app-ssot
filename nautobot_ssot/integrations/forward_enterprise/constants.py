"""Constants used by Forward Enterprise Integration."""

from django.conf import settings

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})

# UI and Styling Constants
TAG_COLOR = "2196f3"

# Default Values for Forward Enterprise Objects
DEFAULT_DEVICE_ROLE = CONFIG.get("forward_enterprise_default_device_role", "Network Device")
DEFAULT_DEVICE_ROLE_COLOR = CONFIG.get("forward_enterprise_default_device_role_color", "ff0000")
DEFAULT_DEVICE_STATUS = CONFIG.get("forward_enterprise_default_device_status", "Active")
DEFAULT_DEVICE_STATUS_COLOR = CONFIG.get("forward_enterprise_default_device_status_color", "ff0000")
DEFAULT_INTERFACE_STATUS = CONFIG.get("forward_enterprise_default_interface_status", "Active")
DEFAULT_PREFIX_STATUS = CONFIG.get("forward_enterprise_default_prefix_status", "Active")
DEFAULT_IPADDRESS_STATUS = CONFIG.get("forward_enterprise_default_ipaddress_status", "Active")
DEFAULT_VLAN_STATUS = CONFIG.get("forward_enterprise_default_vlan_status", "Active")

# System of Record Identifier
SYSTEM_OF_RECORD = "Forward Enterprise"

# API Configuration
DEFAULT_API_TIMEOUT = 30
DEFAULT_PAGE_SIZE = 1000

# VLAN Group Naming
VLAN_GROUP_NAME_TEMPLATE = "Forward Enterprise - {location_name}"
DEFAULT_VLAN_GROUP_NAME = "Forward Enterprise"

# Query Validation Patterns
QUERY_ID_PATTERN = r"^Q_[A-Za-z0-9_]+$"

# Interface Type Mappings (Forward Enterprise to Nautobot)
INTERFACE_TYPE_MAP = {
    "ethernet": "1000base-t",
    "gigabitethernet": "1000base-t",
    "fastethernet": "100base-tx",
    "tengigabitethernet": "10gbase-x-sfpp",
    "fortygigabitethernet": "40gbase-x-qsfpp",
    "hundredgigabitethernet": "100gbase-x-qsfp28",
    "loopback": "virtual",
    "vlan": "virtual",
    "portchannel": "lag",
    "management": "1000base-t",
}

# MTU Constraints
MIN_MTU = 68
MAX_MTU = 9000
DEFAULT_MTU = 1500

# VLAN ID Constraints
MIN_VLAN_ID = 1
MAX_VLAN_ID = 4094
