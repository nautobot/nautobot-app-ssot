"""Defines various constants used throughout the App."""

from django.conf import settings

# Import config vars from nautobot_config.py
PLUGIN_CFG = settings.PLUGINS_CONFIG["nautobot_ssot"]

DNAC_PLATFORM_MAPPER = {
    "IOS": "cisco_ios",
    "IOS-XE": "cisco_ios",
    "NX-OS": "cisco_nxos",
    "IOS-XR": "cisco_xr",
}

BASE_INTERFACE_MAP = {
    "Port-channel": "lag",
    "Tunnel": "virtual",
    "Management": "1000base-t",
    "Ethernet": "1000base-t",
    "FastEthernet": "100base-tx",
    "GigabitEthernet": "1000base-t",
    "TwoGigabitEthernet": "2.5gbase-t",
    "TenGigabitEthernet": "10gbase-x-sfpp",
    "FortyGigabitEthernet": "40gbase-x-qsfpp",
    "FiftyGigabitEthernet": "50gbase-x-sfp28",
    "HundredGigabitEthernet": "100gbase-x-qsfp28",
    "TwentyFiveGigE": "25gbase-x-sfp28",
    "TwoHundredGigabitEthernet": "200gbase-x-qsfp56",
    "FourHundredGigabitEthernet": "400gbase-x-qsfpdd",
    "Wlan-GigabitEthernet": "ieee802.11ax",
    "Virtual-Access": "virtual",
    "Virtual-Template": "virtual",
}
