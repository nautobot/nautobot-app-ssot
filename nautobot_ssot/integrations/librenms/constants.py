"""Constants for LibreNMS SSoT."""

from django.conf import settings

# Import config vars from nautobot_config.py
PLUGIN_CFG = settings.PLUGINS_CONFIG["nautobot_ssot"]

librenms_status_map = {
    0: "Offline",
    1: "Active",
    True: "Active",
    False: "Offline",
}

os_manufacturer_map = {
    "ping": "Generic",
    "linux": "Linux",
    "routeros": "Mikrotik",
    "unifi": "Ubiquiti",
    "airos": "Ubiquiti",
    "proxmox": "Proxmox",
    "hpe-ilo": "HP",
    "cyberpower": "Cyberpower",
    "opnsense": "Opnsense",
    "epmp": "Cambium",
    "tachyon": "Tachyon Networks",
}
