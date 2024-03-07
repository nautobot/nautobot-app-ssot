"""Constants for use with the Infoblox SSoT app."""
from django.conf import settings


def _read_app_config():
    """Provides backward compatible object after integrating into `nautobot_ssot` App."""
    config = settings.PLUGINS_CONFIG["nautobot_ssot"]

    return {
        "NAUTOBOT_INFOBLOX_URL": config.get("infoblox_url"),
        "NAUTOBOT_INFOBLOX_USERNAME": config.get("infoblox_username"),
        "NAUTOBOT_INFOBLOX_PASSWORD": config.get("infoblox_password"),
        "NAUTOBOT_INFOBLOX_VERIFY_SSL": config.get("infoblox_verify_ssl"),
        "NAUTOBOT_INFOBLOX_WAPI_VERSION": config.get("infoblox_wapi_version"),
        "NAUTOBOT_INFOBLOX_NETWORK_VIEW": config.get("infoblox_network_view"),
        "enable_sync_to_infoblox": config.get("infoblox_enable_sync_to_infoblox"),
        "enable_rfc1918_network_containers": config.get("infoblox_enable_rfc1918_network_containers"),
        "default_status": config.get("infoblox_default_status"),
        "infoblox_import_objects": {
            "vlan_views": config.get("infoblox_import_objects_vlan_views"),
            "vlans": config.get("infoblox_import_objects_vlans"),
            "subnets": config.get("infoblox_import_objects_subnets"),
            "subnets_ipv6": config.get("infoblox_import_objects_subnets_ipv6"),
            "ip_addresses": config.get("infoblox_import_objects_ip_addresses"),
        },
        "infoblox_import_subnets": config.get("infoblox_import_subnets"),
        "infoblox_request_timeout": int(config.get("infoblox_request_timeout", 60)),
    }


# Import config vars from nautobot_config.py
PLUGIN_CFG = _read_app_config()
TAG_COLOR = "40bfae"
