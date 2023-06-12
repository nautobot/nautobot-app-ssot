#########################
#                       #
#   Required settings   #
#                       #
#########################

import os
import sys

from nautobot.core.settings import *  # noqa: F401,F403
from nautobot.core.settings_funcs import parse_redis_connection, is_truthy

TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"

# This is a list of valid fully-qualified domain names (FQDNs) for the Nautobot server. Nautobot will not permit write
# access to the server via any other hostnames. The first FQDN in the list will be treated as the preferred name.
#
# Example: ALLOWED_HOSTS = ['nautobot.example.com', 'nautobot.internal.local']
ALLOWED_HOSTS = os.getenv("NAUTOBOT_ALLOWED_HOSTS").split(" ")

# PostgreSQL database configuration. See the Django documentation for a complete list of available parameters:
#   https://docs.djangoproject.com/en/stable/ref/settings/#databases
DATABASES = {
    "default": {
        "NAME": os.getenv("NAUTOBOT_DB_NAME", "nautobot"),  # Database name
        "USER": os.getenv("NAUTOBOT_DB_USER", ""),  # Database username
        "PASSWORD": os.getenv("NAUTOBOT_DB_PASSWORD", ""),  # Datbase password
        "HOST": os.getenv("NAUTOBOT_DB_HOST", "localhost"),  # Database server
        "PORT": os.getenv("NAUTOBOT_DB_PORT", ""),  # Database port (leave blank for default)
        "CONN_MAX_AGE": os.getenv("NAUTOBOT_DB_TIMEOUT", 300),  # Database timeout
        "ENGINE": "django.db.backends.postgresql",  # Database driver (Postgres only supported!)
    }
}

# The django-redis cache is used to establish concurrent locks using Redis. The
# django-rq settings will use the same instance/database by default.
#
# This "default" server is now used by RQ_QUEUES.
# >> See: nautobot.core.settings.RQ_QUEUES
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": parse_redis_connection(redis_database=0),
        "TIMEOUT": 300,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "PASSWORD": os.getenv("NAUTOBOT_REDIS_PASSWORD", ""),
        },
    }
}

# RQ_QUEUES is not set here because it just uses the default that gets imported
# up top via `from nautobot.core.settings import *`.

# REDIS CACHEOPS
CACHEOPS_REDIS = parse_redis_connection(redis_database=1)

# This key is used for secure generation of random numbers and strings. It must never be exposed outside of this file.
# For optimal security, SECRET_KEY should be at least 50 characters in length and contain a mix of letters, numbers, and
# symbols. Nautobot will not run without this defined. For more information, see
# https://docs.djangoproject.com/en/stable/ref/settings/#std:setting-SECRET_KEY
SECRET_KEY = os.getenv("NAUTOBOT_SECRET_KEY", "")

# Enable installed plugins. Add the name of each plugin to the list.
PLUGINS = ["nautobot_ssot", "nautobot_ssot_aristacv", "nautobot_device_lifecycle_mgmt"]

# Plugins configuration settings. These settings are used by various plugins that the user may have installed.
# Each key in the dictionary is the name of an installed plugin and its value is a dictionary of settings.
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "hide_example_jobs": True,  # defaults to False if unspecified
    },
    "nautobot_ssot_aristacv": {
        "cvp_token": os.getenv("NAUTOBOT_ARISTACV_TOKEN", ""),
        "cvp_host": os.getenv("NAUTOBOT_ARISTACV_HOST", ""),
        "cvp_port": os.getenv("NAUTOBOT_ARISTACV_PORT", 443),
        "cvp_user": os.getenv("NAUTOBOT_ARISTACV_USERNAME", ""),
        "cvp_password": os.getenv("NAUTOBOT_ARISTACV_PASSWORD", ""),
        "verify": is_truthy(os.getenv("NAUTOBOT_ARISTACV_VERIFY", True)),
        "from_cloudvision_default_site": "cloudvision_imported",
        "from_cloudvision_default_device_role": "network",
        "from_cloudvision_default_device_role_color": "ff0000",
        "delete_devices_on_sync": is_truthy(os.getenv("NAUTOBOT_ARISTACV_DELETE_ON_SYNC", False)),
        "apply_import_tag": is_truthy(os.getenv("NAUTOBOT_ARISTACV_IMPORT_TAG", False)),
        "import_active": is_truthy(os.getenv("NAUTOBOT_ARISTACV_IMPORT_ACTIVE", False)),
        "create_controller": is_truthy(os.getenv("NAUTOBOT_ARISTACV_CREATE_CONTROLLER", False)),
        "controller_site": os.getenv("NAUTOBOT_ARISTACV_CONTROLLER_SITE", ""),
        "hostname_patterns": [[r"(?P<site>\w{2,3}\d+)-(?P<role>\w+)-\d+"]],
        "site_mappings": {"ams01": "Amsterdam", "atl01": "Atlanta"},
        "role_mappings": {
            "bb": "backbone",
            "edge": "edge",
            "dist": "distribution",
            "leaf": "leaf",
            "rtr": "router",
            "spine": "spine",
        },
    },
}
