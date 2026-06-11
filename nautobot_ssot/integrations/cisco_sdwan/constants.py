"""Constants for the Cisco SD-WAN SSoT integration."""

from django.conf import settings
from nautobot.dcim.choices import InterfaceTypeChoices

APP_SETTINGS = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})

# Name used for the Job's Meta.data_source. The contrib metadata feature derives the
# MetadataType name from this value ("Last sync from <DATA_SOURCE_NAME>"), so the
# Nautobot adapter querysets reference it as well.
DATA_SOURCE_NAME = "Cisco SD-WAN"

DEFAULT_INTERFACE_TYPE = APP_SETTINGS.get("cisco_sdwan_default_interface_type", InterfaceTypeChoices.TYPE_OTHER)
DEFAULT_INTERFACE_STATUS = APP_SETTINGS.get("cisco_sdwan_default_interface_status", "Active")
DEFAULT_IPADDRESS_STATUS = APP_SETTINGS.get("cisco_sdwan_default_ipaddress_status", "Active")
DEVICE_RETIRED_STATUS = APP_SETTINGS.get("cisco_sdwan_device_retired_status", "Retired")
SDWAN_IF_UP_STATES = APP_SETTINGS.get("cisco_sdwan_if_up_states", ["if-state-up", "up"])
SDWAN_NULL_IP_ADDRESSES = APP_SETTINGS.get("cisco_sdwan_null_ip_addresses", ["-", "0.0.0.0"])  # noqa: S104
NULL_MTU_VALUES = APP_SETTINGS.get("cisco_sdwan_null_mtu_values", ["0"])
EXCLUDED_INTERFACES = APP_SETTINGS.get("cisco_sdwan_excluded_interfaces", ["Loopback65528", "Loopback65529"])
EXCLUDED_PREFIXES = APP_SETTINGS.get("cisco_sdwan_excluded_prefixes", ["169.254.0.0/16"])
SOFTWARE_VERSION_PLATFORM_NAME = APP_SETTINGS.get("cisco_sdwan_software_version_platform_name", "cisco_xe")
PRIMARY_IP_INTERFACES = APP_SETTINGS.get("cisco_sdwan_primary_ip_interfaces", ["system"])
