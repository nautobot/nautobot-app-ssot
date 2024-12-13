"""Constants for LibreNMS SSoT."""

from django.conf import settings

# Import config vars from nautobot_config.py
PLUGIN_CFG = settings.PLUGINS_CONFIG["nautobot_ssot"]

librenms_status_map = {
    1: "Active",
    2: "Offline",
    True: "Active",
    False: "Offline",
}

os_manufacturer_map = {
    "ping": "Generic",
    "linux": "Linux",
    "routeros": "Mikrotik",
    "unifi": "Ubiquiti",
}
