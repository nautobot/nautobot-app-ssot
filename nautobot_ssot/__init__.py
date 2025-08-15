"""App declaration for nautobot_ssot."""

import logging
import os
from importlib import metadata

from django.conf import settings
from nautobot.core.settings_funcs import is_truthy
from nautobot.extras.plugins import NautobotAppConfig

from nautobot_ssot.integrations.utils import each_enabled_integration_module

logger = logging.getLogger("nautobot.ssot")
__version__ = metadata.version(__name__)


_CONFLICTING_APP_NAMES = [
    "nautobot_ssot_aci",
    "nautobot_ssot_aristacv",
    "nautobot_ssot_bootstrap",
    "nautobot_ssot_citrix_adm",
    "nautobot_ssot_device42",
    "nautobot_ssot_dna_center",
    "nautobot_ssot_infoblox",
    "nautobot_ssot_ipfabric",
    "nautobot_ssot_itential",
    "nautobot_ssot_meraki",
    "nautobot_ssot_servicenow",
    "nautobot_ssot_solarwinds",
]


def _check_for_conflicting_apps():
    intersection = set(_CONFLICTING_APP_NAMES).intersection(set(settings.PLUGINS))
    if intersection:
        raise RuntimeError(
            f"The following apps are installed and conflict with `nautobot-ssot`: {', '.join(intersection)}."
            "See: https://docs.nautobot.com/projects/ssot/en/latest/admin/upgrade/#potential-apps-conflicts"
        )


if not is_truthy(os.getenv("NAUTOBOT_SSOT_ALLOW_CONFLICTING_APPS", "False")):
    _check_for_conflicting_apps()


class NautobotSSOTAppConfig(NautobotAppConfig):
    """App configuration for the nautobot_ssot app."""

    name = "nautobot_ssot"
    verbose_name = "Single Source of Truth"
    version = __version__
    author = "Network to Code, LLC"
    description = "Nautobot app that enables Single Source of Truth.  Allows users to aggregate distributed data sources and/or distribute Nautobot data to other data sources such as databases and SDN controllers."
    base_url = "ssot"
    required_settings = []
    min_version = "2.1.0"
    max_version = "2.9999"
    default_settings = {
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
        "citrix_adm_update_sites": True,
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
        "dna_center_import_global": True,
        "dna_center_import_merakis": False,
        "dna_center_update_locations": True,
        "dna_center_show_failures": True,
        "enable_aci": False,
        "enable_aristacv": False,
        "enable_bootstrap": False,
        "enable_device42": False,
        "enable_dna_center": False,
        "enable_citrix_adm": False,
        "enable_infoblox": False,
        "enable_ipfabric": False,
        "enable_librenms": False,
        "enable_meraki": False,
        "enable_servicenow": False,
        "enable_slurpit": False,
        "enable_solarwinds": False,
        "enable_itential": False,
        "hide_example_jobs": True,
        "ipfabric_api_token": "",
        "ipfabric_host": "",
        "ipfabric_ssl_verify": True,
        "ipfabric_timeout": 15,
        "ipfabric_nautobot_host": "",
        "ipfabric_sync_ipf_dev_type_to_role": True,
        "servicenow_instance": "",
        "servicenow_password": "",
        "servicenow_username": "",
        "enable_global_search": True,
    }
    caching_config = {}
    config_view_name = "plugins:nautobot_ssot:config"
    docs_view_name = "plugins:nautobot_ssot:docs"

    def __init__(self, *args, **kwargs):
        """Initialize a NautobotSSOTAppConfig instance and set default attributes."""
        super().__init__(*args, **kwargs)
        # Only set searchable_models if enabled in config
        if settings.PLUGINS_CONFIG["nautobot_ssot"].get("enable_global_search", True):
            self.searchable_models = [
                "Sync",
                "SyncLogEntry",
            ]

    def ready(self):
        """Trigger callback when database is ready."""
        super().ready()
        for module in each_enabled_integration_module("signals"):
            logger.debug("Registering signals for %s", module.__file__)
            module.register_signals(self)


config = NautobotSSOTAppConfig  # pylint:disable=invalid-name
