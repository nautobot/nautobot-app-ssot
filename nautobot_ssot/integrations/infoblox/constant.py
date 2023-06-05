"""Constants for use with the Infoblox SSoT plugin."""
from django.conf import settings


def _read_plugin_config():
    """Provides backward compatible object after integrating into `nautobot_ssot` App."""
    config = settings.PLUGINS_CONFIG["nautobot_ssot"]

    return {
        "NAUTOBOT_INFOBLOX_URL": config["infoblox_url"],
        "NAUTOBOT_INFOBLOX_USERNAME": config["infoblox_username"],
        "NAUTOBOT_INFOBLOX_PASSWORD": config["infoblox_password"],
        "NAUTOBOT_INFOBLOX_VERIFY_SSL": config["infoblox_verify_ssl"],
        "NAUTOBOT_INFOBLOX_WAPI_VERSION": config["infoblox_wapi_version"],
        "enable_sync_to_infoblox": config["infoblox_enable_sync_to_infoblox"],
        "enable_rfc1918_network_containers": config["infoblox_enable_rfc1918_network_containers"],
        "default_status": config["infoblox_default_status"],
        "infoblox_import_objects": {
            "vlan_views": config["infoblox_import_objects_vlan_views"],
            "vlans": config["infoblox_import_objects_vlans"],
            "subnets": config["infoblox_import_objects_subnets"],
            "ip_addresses": config["infoblox_import_objects_ip_addresses"],
        },
        "infoblox_import_subnets": config["infoblox_import_subnets"],
    }


# Import config vars from nautobot_config.py
PLUGIN_CFG = _read_plugin_config()
TAG_COLOR = "40bfae"
