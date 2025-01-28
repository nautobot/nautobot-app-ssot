"""Nautobot development configuration file."""

import os
import sys

from nautobot.core.settings import *  # noqa: F403  # pylint: disable=wildcard-import,unused-wildcard-import
from nautobot.core.settings_funcs import is_truthy

#
# Debug
#

DEBUG = is_truthy(os.getenv("NAUTOBOT_DEBUG", "false"))
_TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"

if DEBUG and not _TESTING:
    DEBUG_TOOLBAR_CONFIG = {"SHOW_TOOLBAR_CALLBACK": lambda _request: True}

    if "debug_toolbar" not in INSTALLED_APPS:  # noqa: F405
        INSTALLED_APPS.append("debug_toolbar")  # noqa: F405
    if "debug_toolbar.middleware.DebugToolbarMiddleware" not in MIDDLEWARE:  # noqa: F405
        MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405

#
# Misc. settings
#

ALLOWED_HOSTS = os.getenv("NAUTOBOT_ALLOWED_HOSTS", "").split(" ")
SECRET_KEY = os.getenv("NAUTOBOT_SECRET_KEY", "")

#
# Database
#

nautobot_db_engine = os.getenv("NAUTOBOT_DB_ENGINE", "django.db.backends.postgresql")
default_db_settings = {
    "django.db.backends.postgresql": {
        "NAUTOBOT_DB_PORT": "5432",
    },
    "django.db.backends.mysql": {
        "NAUTOBOT_DB_PORT": "3306",
    },
}
DATABASES = {
    "default": {
        "NAME": os.getenv("NAUTOBOT_DB_NAME", "nautobot"),  # Database name
        "USER": os.getenv("NAUTOBOT_DB_USER", ""),  # Database username
        "PASSWORD": os.getenv("NAUTOBOT_DB_PASSWORD", ""),  # Database password
        "HOST": os.getenv("NAUTOBOT_DB_HOST", "localhost"),  # Database server
        "PORT": os.getenv(
            "NAUTOBOT_DB_PORT",
            default_db_settings[nautobot_db_engine]["NAUTOBOT_DB_PORT"],
        ),  # Database port, default to postgres
        "CONN_MAX_AGE": int(os.getenv("NAUTOBOT_DB_TIMEOUT", "300")),  # Database timeout
        "ENGINE": nautobot_db_engine,
    }
}

# Ensure proper Unicode handling for MySQL
if DATABASES["default"]["ENGINE"] == "django.db.backends.mysql":
    DATABASES["default"]["OPTIONS"] = {"charset": "utf8mb4"}

#
# Redis
#

# The django-redis cache is used to establish concurrent locks using Redis.
# Inherited from nautobot.core.settings
# CACHES = {....}

#
# Celery settings are not defined here because they can be overloaded with
# environment variables. By default they use `CACHES["default"]["LOCATION"]`.
#

#
# Logging
#

LOG_LEVEL = "DEBUG" if DEBUG else "INFO"

# Verbose logging during normal development operation, but quiet logging during unit test execution
if not _TESTING:
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "normal": {
                "format": "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s : %(message)s",
                "datefmt": "%H:%M:%S",
            },
            "verbose": {
                "format": "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)-20s %(filename)-15s %(funcName)30s() : %(message)s",
                "datefmt": "%H:%M:%S",
            },
        },
        "handlers": {
            "normal_console": {
                "level": "INFO",
                "class": "logging.StreamHandler",
                "formatter": "normal",
            },
            "verbose_console": {
                "level": "DEBUG",
                "class": "logging.StreamHandler",
                "formatter": "verbose",
            },
        },
        "loggers": {
            "django": {"handlers": ["normal_console"], "level": "INFO"},
            "nautobot": {
                "handlers": ["verbose_console" if DEBUG else "normal_console"],
                "level": LOG_LEVEL,
            },
        },
    }

#
# Apps
#

# Enable installed Apps. Add the name of each App to the list.
PLUGINS = [
    # "nautobot_chatops",
    "nautobot_device_lifecycle_mgmt",
    "nautobot_ssot",
]

# Apps configuration settings. These settings are used by various Apps that the user may have installed.
# Each key in the dictionary is the name of an installed App and its value is a dictionary of settings.
PLUGINS_CONFIG = {
    # "nautobot_chatops": {
    #     "enable_slack": True,
    #     "slack_api_token": os.getenv("SLACK_API_TOKEN"),
    #     "slack_signing_secret": os.getenv("SLACK_SIGNING_SECRET"),
    #     "session_cache_timeout": 3600,
    # },
    "nautobot_ssot": {
        # Tag which will be created and applied to all synchronized objects.
        "aci_tag": os.getenv("NAUTOBOT_SSOT_ACI_TAG"),
        "aci_tag_color": os.getenv("NAUTOBOT_SSOT_ACI_TAG_COLOR"),
        # Tags indicating state applied to synchronized interfaces.
        "aci_tag_up": os.getenv("NAUTOBOT_SSOT_ACI_TAG_UP"),
        "aci_tag_up_color": os.getenv("NAUTOBOT_SSOT_ACI_TAG_UP_COLOR"),
        "aci_tag_down": os.getenv("NAUTOBOT_SSOT_ACI_TAG_DOWN"),
        "aci_tag_down_color": os.getenv("NAUTOBOT_SSOT_ACI_TAG_DOWN_COLOR"),
        # Manufacturer name. Specify existing, or a new one with this name will be created.
        "aci_manufacturer_name": os.getenv("NAUTOBOT_SSOT_ACI_MANUFACTURER_NAME"),
        # Exclude any tenants you would not like to bring over from ACI.
        "aci_ignore_tenants": os.getenv("NAUTOBOT_SSOT_ACI_IGNORE_TENANTS", "").split(","),
        # The below value will appear in the Comments field on objects created in Nautobot
        "aci_comments": os.getenv("NAUTOBOT_SSOT_ACI_COMMENTS"),
        "aristacv_apply_import_tag": is_truthy(os.getenv("NAUTOBOT_ARISTACV_IMPORT_TAG", "false")),
        "aristacv_controller_site": os.getenv("NAUTOBOT_ARISTACV_CONTROLLER_SITE", ""),
        "aristacv_create_controller": is_truthy(os.getenv("NAUTOBOT_ARISTACV_CREATE_CONTROLLER", "false")),
        "aristacv_cvaas_url": os.getenv("NAUTOBOT_ARISTACV_CVAAS_URL", "www.arista.io:443"),
        "aristacv_cvp_host": os.getenv("NAUTOBOT_ARISTACV_CVP_HOST", ""),
        "aristacv_cvp_password": os.getenv("NAUTOBOT_ARISTACV_CVP_PASSWORD", ""),
        "aristacv_cvp_port": os.getenv("NAUTOBOT_ARISTACV_CVP_PORT", "443"),
        "aristacv_cvp_token": os.getenv("NAUTOBOT_ARISTACV_CVP_TOKEN", ""),
        "aristacv_cvp_user": os.getenv("NAUTOBOT_ARISTACV_CVP_USERNAME", ""),
        "aristacv_delete_devices_on_sync": is_truthy(os.getenv("NAUTOBOT_ARISTACV_DELETE_ON_SYNC", "false")),
        "aristacv_from_cloudvision_default_device_role": "network",
        "aristacv_from_cloudvision_default_device_role_color": "ff0000",
        "aristacv_from_cloudvision_default_site": "cloudvision_imported",
        "aristacv_hostname_patterns": [r"(?P<site>\w{2,3}\d+)-(?P<role>\w+)-\d+"],
        "aristacv_import_active": is_truthy(os.getenv("NAUTOBOT_ARISTACV_IMPORT_ACTIVE", "false")),
        "aristacv_role_mappings": {
            "bb": "backbone",
            "edge": "edge",
            "dist": "distribution",
            "leaf": "leaf",
            "rtr": "router",
            "spine": "spine",
        },
        "aristacv_site_mappings": {
            "ams01": "Amsterdam",
            "atl01": "Atlanta",
        },
        "aristacv_verify": is_truthy(os.getenv("NAUTOBOT_ARISTACV_VERIFY", "true")),
        "bootstrap_nautobot_environment_branch": os.getenv("NAUTOBOT_BOOTSTRAP_SSOT_ENVIRONMENT_BRANCH", "develop"),
        "bootstrap_models_to_sync": {
            "secret": True,
            "secrets_group": True,
            "git_repository": True,
            "dynamic_group": True,
            "computed_field": True,
            "tag": True,
            "graph_ql_query": True,
            "software": False,
            "software_image": False,
            "validated_software": False,
            "tenant_group": True,
            "tenant": True,
            "role": True,
            "manufacturer": True,
            "platform": True,
            "location_type": True,
            "location": True,
            "team": True,
            "contact": True,
            "provider": True,
            "provider_network": True,
            "circuit_type": True,
            "circuit": True,
            "circuit_termination": True,
            "namespace": True,
            "rir": True,
            "vlan_group": True,
            "vlan": True,
            "vrf": True,
            "prefix": True,
            "scheduled_job": True,
        },
        "citrix_adm_update_sites": is_truthy(os.getenv("NAUTOBOT_SSOT_CITRIX_ADM_UPDATE_SITES", "true")),
        "enable_aci": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_ACI")),
        "enable_aristacv": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_ARISTACV")),
        "enable_bootstrap": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_BOOTSTRAP", "false")),
        "enable_citrix_adm": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_CITRIX_ADM")),
        "enable_device42": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_DEVICE42")),
        "enable_dna_center": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_DNA_CENTER")),
        "enable_infoblox": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_INFOBLOX")),
        "enable_ipfabric": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_IPFABRIC")),
        "enable_itential": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_ITENTIAL")),
        "enable_librenms": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_LIBRENMS", "false")),
        "enable_meraki": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_MERAKI")),
        "enable_servicenow": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_SERVICENOW")),
        "enable_slurpit": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_SLURPIT")),
        "enable_solarwinds": is_truthy(os.getenv("NAUTOBOT_SSOT_ENABLE_SOLARWINDS")),
        "hide_example_jobs": is_truthy(os.getenv("NAUTOBOT_SSOT_HIDE_EXAMPLE_JOBS")),
        "device42_defaults": {
            "site_status": "Active",
            "rack_status": "Active",
            "device_role": "Unknown",
        },
        "device42_delete_on_sync": False,
        "device42_use_dns": True,
        "device42_customer_is_facility": True,
        "device42_facility_prepend": "",
        "device42_role_prepend": "",
        "device42_ignore_tag": "",
        "device42_hostname_mapping": [],
        "dna_center_import_global": is_truthy(os.getenv("NAUTOBOT_DNAC_SSOT_DNA_CENTER_IMPORT_GLOBAL", "true")),
        "dna_center_import_merakis": is_truthy(os.getenv("NAUTOBOT_DNAC_SSOT_DNA_CENTER_IMPORT_MERAKIS", "false")),
        "dna_center_delete_locations": is_truthy(os.getenv("NAUTOBOT_DNAC_SSOT_DNA_CENTER_DELETE_LOCATIONS", "true")),
        "dna_center_update_locations": is_truthy(os.getenv("NAUTOBOT_DNAC_SSOT_DNA_CENTER_UPDATE_LOCATIONS", "true")),
        "dna_center_show_failures": is_truthy(os.getenv("NAUTOBOT_DNAC_SSOT_DNA_CENTER_SHOW_FAILURES", "true")),
        "infoblox_default_status": os.getenv("NAUTOBOT_SSOT_INFOBLOX_DEFAULT_STATUS", "active"),
        "infoblox_enable_sync_to_infoblox": is_truthy(os.getenv("NAUTOBOT_SSOT_INFOBLOX_ENABLE_SYNC_TO_INFOBLOX")),
        "infoblox_import_objects_ip_addresses": is_truthy(
            os.getenv("NAUTOBOT_SSOT_INFOBLOX_IMPORT_OBJECTS_IP_ADDRESSES")
        ),
        "infoblox_import_objects_subnets": is_truthy(os.getenv("NAUTOBOT_SSOT_INFOBLOX_IMPORT_OBJECTS_SUBNETS")),
        "infoblox_import_objects_subnets_ipv6": is_truthy(
            os.getenv("NAUTOBOT_SSOT_INFOBLOX_IMPORT_OBJECTS_SUBNETS_IPV6")
        ),
        "infoblox_import_objects_vlan_views": is_truthy(os.getenv("NAUTOBOT_SSOT_INFOBLOX_IMPORT_OBJECTS_VLAN_VIEWS")),
        "infoblox_import_objects_vlans": is_truthy(os.getenv("NAUTOBOT_SSOT_INFOBLOX_IMPORT_OBJECTS_VLANS")),
        "infoblox_import_subnets": [x for x in os.getenv("NAUTOBOT_SSOT_INFOBLOX_IMPORT_SUBNETS", "").split(",") if x],
        "infoblox_password": os.getenv("NAUTOBOT_SSOT_INFOBLOX_PASSWORD"),
        "infoblox_url": os.getenv("NAUTOBOT_SSOT_INFOBLOX_URL"),
        "infoblox_username": os.getenv("NAUTOBOT_SSOT_INFOBLOX_USERNAME"),
        "infoblox_verify_ssl": is_truthy(os.getenv("NAUTOBOT_SSOT_INFOBLOX_VERIFY_SSL", "true")),
        "infoblox_wapi_version": os.getenv("NAUTOBOT_SSOT_INFOBLOX_WAPI_VERSION", "v2.12"),
        "infoblox_network_view": os.getenv("NAUTOBOT_SSOT_INFOBLOX_NETWORK_VIEW", ""),
        "servicenow_instance": os.getenv("SERVICENOW_INSTANCE", ""),
        "servicenow_password": os.getenv("SERVICENOW_PASSWORD", ""),
        "servicenow_username": os.getenv("SERVICENOW_USERNAME", ""),
    },
    "nautobot_device_lifecycle_mgmt": {
        "barchart_bar_width": float(os.environ.get("BARCHART_BAR_WIDTH", 0.1)),
        "barchart_width": int(os.environ.get("BARCHART_WIDTH", 12)),
        "barchart_height": int(os.environ.get("BARCHART_HEIGHT", 5)),
    },
}

METRICS_ENABLED = True
