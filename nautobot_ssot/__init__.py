"""App declaration for nautobot_ssot."""

import os
from importlib import metadata


from django.conf import settings
from nautobot.extras.plugins import NautobotAppConfig
from nautobot.core.settings_funcs import is_truthy
import packaging

from nautobot_ssot.integrations.utils import each_enabled_integration_module
from nautobot_ssot.utils import logger

__version__ = metadata.version(__name__)


_CONFLICTING_APP_NAMES = [
    "nautobot_ssot_aci",
    "nautobot_ssot_aristacv",
    "nautobot_ssot_device42",
    "nautobot_ssot_infoblox",
    "nautobot_ssot_ipfabric",
    "nautobot_ssot_servicenow",
]

_MIN_NAUTOBOT_VERSION = {
    "nautobot_ssot_aristacv": "2.1",
    "nautobot_ssot_infoblox": "2.1",
}


def _check_min_nautobot_version_met():
    incompatible_apps_msg = []
    nautobot_version = metadata.version("nautobot")
    for app, nb_ver in _MIN_NAUTOBOT_VERSION.items():
        if packaging.version.parse(nb_ver) > packaging.version.parse(nautobot_version):
            incompatible_apps_msg.append(f"The `{app}` requires Nautobot version {nb_ver} or higher.\n")

    if incompatible_apps_msg:
        raise RuntimeError(
            f"This version of Nautobot ({nautobot_version}) does not meet minimum requirements for the following apps:\n {''.join(incompatible_apps_msg)}."
            "See: https://docs.nautobot.com/projects/ssot/en/latest/admin/upgrade/#potential-apps-conflicts"
        )


def _check_for_conflicting_apps():
    intersection = set(_CONFLICTING_APP_NAMES).intersection(set(settings.PLUGINS))
    if intersection:
        raise RuntimeError(
            f"The following apps are installed and conflict with `nautobot-ssot`: {', '.join(intersection)}."
            "See: https://docs.nautobot.com/projects/ssot/en/latest/admin/upgrade/#potential-apps-conflicts"
        )


if not is_truthy(os.getenv("NAUTOBOT_SSOT_ALLOW_CONFLICTING_APPS", "False")):
    _check_for_conflicting_apps()

_check_min_nautobot_version_met()


class NautobotSSOTAppConfig(NautobotAppConfig):
    """App configuration for the nautobot_ssot app."""

    name = "nautobot_ssot"
    verbose_name = "Single Source of Truth"
    version = __version__
    author = "Network to Code, LLC"
    description = "Nautobot app that enables Single Source of Truth.  Allows users to aggregate distributed data sources and/or distribute Nautobot data to other data sources such as databases and SDN controllers."
    base_url = "ssot"
    required_settings = []
    min_version = "2.0.0"
    max_version = "2.9999"
    default_settings = {
        "aci_apics": [],
        "aci_tag": "",
        "aci_tag_color": "",
        "aci_tag_up": "",
        "aci_tag_up_color": "",
        "aci_tag_down": "",
        "aci_tag_down_color": "",
        "aci_manufacturer_name": "",
        "aci_ignore_tenants": [],
        "aci_comments": "",
        "aci_site": "",
        "aristacv_apply_import_tag": False,
        "aristacv_controller_site": "",
        "aristacv_create_controller": False,
        "aristacv_cvaas_url": "www.arista.io:443",
        "aristacv_cvp_host": "",
        "aristacv_cvp_password": "",
        "aristacv_cvp_port": "443",
        "aristacv_cvp_token": "",
        "aristacv_cvp_user": "",
        "aristacv_delete_devices_on_sync": False,
        "aristacv_from_cloudvision_default_device_role": "",
        "aristacv_from_cloudvision_default_device_role_color": "",
        "aristacv_from_cloudvision_default_site": "",
        "aristacv_hostname_patterns": [],
        "aristacv_import_active": False,
        "aristacv_external_integration_name": "",
        "aristacv_role_mappings": {},
        "aristacv_site_mappings": {},
        "aristacv_verify": True,
        "device42_host": "",
        "device42_username": "",
        "device42_password": "",
        "device42_defaults": {},
        "device42_delete_on_sync": False,
        "device42_use_dns": True,
        "device42_customer_is_facility": True,
        "device42_facility_prepend": "",
        "device42_role_prepend": "",
        "device42_ignore_tag": "",
        "device42_hostname_mapping": [],
        "enable_aci": False,
        "enable_aristacv": False,
        "enable_device42": False,
        "enable_infoblox": False,
        "enable_ipfabric": False,
        "enable_servicenow": False,
        "enable_itential": False,
        "hide_example_jobs": True,
        "ipfabric_api_token": "",
        "ipfabric_host": "",
        "ipfabric_ssl_verify": True,
        "ipfabric_timeout": 15,
        "ipfabric_nautobot_host": "",
        "servicenow_instance": "",
        "servicenow_password": "",
        "servicenow_username": "",
    }
    caching_config = {}
    config_view_name = "plugins:nautobot_ssot:config"

    def ready(self):
        """Trigger callback when database is ready."""
        super().ready()

        for module in each_enabled_integration_module("signals"):
            logger.debug("Registering signals for %s", module.__file__)
            module.register_signals(self)


config = NautobotSSOTAppConfig  # pylint:disable=invalid-name
