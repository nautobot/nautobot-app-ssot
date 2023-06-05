"""Nautobot development configuration file."""
# pylint: disable=invalid-envvar-default
import os
import sys
import json

from nautobot.core.settings import *  # noqa: F403
from nautobot.core.settings_funcs import parse_redis_connection


def _get_env(name: str, default="") -> str:
    return os.getenv(f"NAUTOBOT_SSOT_{name}", default)


def _get_bool_env(name: str, default=False) -> bool:
    return bool(json.loads(_get_env(name, str(default)).lower()))


#
# Misc. settings
#

ALLOWED_HOSTS = os.getenv("NAUTOBOT_ALLOWED_HOSTS", "").split(" ")
SECRET_KEY = os.getenv("NAUTOBOT_SECRET_KEY", "")


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
            "NAUTOBOT_DB_PORT", default_db_settings[nautobot_db_engine]["NAUTOBOT_DB_PORT"]
        ),  # Database port, default to postgres
        "CONN_MAX_AGE": int(os.getenv("NAUTOBOT_DB_TIMEOUT", 300)),  # Database timeout
        "ENGINE": nautobot_db_engine,
    }
}

# Ensure proper Unicode handling for MySQL
if DATABASES["default"]["ENGINE"] == "django.db.backends.mysql":
    DATABASES["default"]["OPTIONS"] = {"charset": "utf8mb4"}

#
# Debug
#

DEBUG = True

# Django Debug Toolbar
DEBUG_TOOLBAR_CONFIG = {"SHOW_TOOLBAR_CALLBACK": lambda _request: DEBUG and not TESTING}

if DEBUG and "debug_toolbar" not in INSTALLED_APPS:  # noqa: F405
    INSTALLED_APPS.append("debug_toolbar")  # noqa: F405
if DEBUG and "debug_toolbar.middleware.DebugToolbarMiddleware" not in MIDDLEWARE:  # noqa: F405
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405

#
# Logging
#

LOG_LEVEL = "DEBUG" if DEBUG else "INFO"

TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"

# Verbose logging during normal development operation, but quiet logging during unit test execution
if not TESTING:
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "normal": {
                "format": "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s :\n  %(message)s",
                "datefmt": "%H:%M:%S",
            },
            "verbose": {
                "format": "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)-20s %(filename)-15s %(funcName)30s() :\n  %(message)s",
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
# Redis
#

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
        },
    }
}

# RQ_QUEUES is not set here because it just uses the default that gets imported
# up top via `from nautobot.core.settings import *`.

# Redis Cacheops
CACHEOPS_REDIS = parse_redis_connection(redis_database=1)

#
# Celery settings are not defined here because they can be overloaded with
# environment variables. By default they use `CACHES["default"]["LOCATION"]`.
#

# Enable installed plugins. Add the name of each plugin to the list.
PLUGINS = ["nautobot_ssot"]

# Plugins configuration settings. These settings are used by various plugins that the user may have installed.
# Each key in the dictionary is the name of an installed plugin and its value is a dictionary of settings.
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_infoblox": _get_bool_env("ENABLE_INFOBLOX"),
        "hide_example_jobs": _get_bool_env("HIDE_EXAMPLE_JOBS"),
        "infoblox_default_status": _get_env("INFOBLOX_DEFAULT_STATUS", "active"),
        "infoblox_enable_rfc1918_network_containers": _get_bool_env("INFOBLOX_ENABLE_RFC1918_NETWORK_CONTAINERS"),
        "infoblox_enable_sync_to_infoblox": _get_bool_env("INFOBLOX_ENABLE_SYNC_TO_INFOBLOX"),
        "infoblox_import_objects_ip_addresses": _get_bool_env("INFOBLOX_IMPORT_OBJECTS_IP_ADDRESSES"),
        "infoblox_import_objects_subnets": _get_bool_env("INFOBLOX_IMPORT_OBJECTS_SUBNETS"),
        "infoblox_import_objects_vlan_views": _get_bool_env("INFOBLOX_IMPORT_OBJECTS_VLAN_VIEWS"),
        "infoblox_import_objects_vlans": _get_bool_env("INFOBLOX_IMPORT_OBJECTS_VLANS"),
        "infoblox_import_subnets": _get_env("INFOBLOX_IMPORT_SUBNETS").split(","),
        "infoblox_password": _get_env("INFOBLOX_PASSWORD"),
        "infoblox_url": _get_env("INFOBLOX_URL"),
        "infoblox_username": _get_env("INFOBLOX_USERNAME"),
        "infoblox_verify_ssl": _get_bool_env("INFOBLOX_VERIFY_SSL", True),
        "infoblox_wapi_version": _get_env("INFOBLOX_WAPI_VERSION", "v2.12"),
    },
}

METRICS_ENABLED = True
