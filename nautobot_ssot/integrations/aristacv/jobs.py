# pylint: disable=invalid-name,too-few-public-methods
"""Jobs for CloudVision integration with SSoT app."""
from typing import Mapping
from typing import Optional
from urllib.parse import urlparse

from django.templatetags.static import static
from django.urls import reverse
from nautobot.core.settings_funcs import is_truthy
from nautobot.core.utils.lookup import get_route_for_model
from nautobot.dcim.models import DeviceType
from nautobot.extras.choices import SecretsGroupAccessTypeChoices
from nautobot.extras.choices import SecretsGroupSecretTypeChoices
from nautobot.extras.jobs import BooleanVar
from nautobot.extras.jobs import Job
from nautobot.extras.jobs import ObjectVar
from nautobot.extras.models import ExternalIntegration
from nautobot.extras.models import SecretsGroup

from nautobot_ssot.integrations.aristacv.constant import APP_SETTINGS
from nautobot_ssot.integrations.aristacv.diffsync.adapters.cloudvision import CloudvisionAdapter
from nautobot_ssot.integrations.aristacv.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.integrations.aristacv.diffsync.models import nautobot
from nautobot_ssot.integrations.aristacv.utils.cloudvision import CloudvisionApi
from nautobot_ssot.jobs.base import DataMapping
from nautobot_ssot.jobs.base import DataSource
from nautobot_ssot.jobs.base import DataTarget

name = "SSoT - Arista CloudVision"  # pylint: disable=invalid-name


def _get_settings(source: Optional[ExternalIntegration]) -> dict:
    source_config = source.extra_config if source and isinstance(source.extra_config, Mapping) else {}
    # On premise is a default behavior for ExternalIntegration
    is_on_prem = bool(source_config.get("is_on_prem", True) if source else APP_SETTINGS.get("aristacv_cvp_host"))

    settings = {
        "is_on_prem": is_on_prem,
        "delete_devices_on_sync": is_truthy(
            APP_SETTINGS.get("aristacv_delete_devices_on_sync", nautobot.DEFAULT_DELETE_DEVICES_ON_SYNC)
        ),
        "from_cloudvision_default_site": APP_SETTINGS.get(
            "aristacv_from_cloudvision_default_site", nautobot.DEFAULT_SITE
        ),
        "from_cloudvision_default_device_role": APP_SETTINGS.get(
            "aristacv_from_cloudvision_default_device_role", nautobot.DEFAULT_DEVICE_ROLE
        ),
        "from_cloudvision_default_device_role_color": APP_SETTINGS.get(
            "aristacv_from_cloudvision_default_device_role_color", nautobot.DEFAULT_DEVICE_ROLE_COLOR
        ),
        "apply_import_tag": is_truthy(APP_SETTINGS.get("aristacv_apply_import_tag", nautobot.APPLY_IMPORT_TAG)),
        "import_active": APP_SETTINGS.get("aristacv_import_active"),
        "verify": APP_SETTINGS.get("aristacv_verify"),
        "cvp_host": APP_SETTINGS.get("aristacv_cvp_host"),
        "cvp_user": APP_SETTINGS.get("aristacv_cvp_user"),
        "cvp_password": APP_SETTINGS.get("aristacv_cvp_password"),
        "cvp_token": APP_SETTINGS.get("aristacv_cvp_token"),
        "cvp_port": APP_SETTINGS.get("aristacv_cvp_port"),
    }

    if not source:
        return settings

    if isinstance(source.verify_ssl, bool):
        settings["verify"] = source.verify_ssl

    if is_on_prem:
        parsed_url = urlparse(source.remote_url)  # type: ignore
        if parsed_url:
            settings["cvp_host"] = parsed_url.hostname
            settings["cvp_port"] = parsed_url.port
    else:
        settings["cvaas_url"] = source.remote_url
        return settings

    secrets_group: SecretsGroup = source.secrets_group  # type: ignore
    if not secrets_group:
        return settings

    settings["cvp_user"] = secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
    )
    settings["cvp_password"] = secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
    )
    settings["cvp_token"] = secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
    )

    settings.update(source_config)

    return settings


class MissingConfigSetting(Exception):
    """Exception raised for missing configuration settings.

    Attributes:
        message (str): Returned explanation of Error.
    """

    def __init__(self, setting):
        """Initialize Exception with Setting that is missing and message."""
        self.setting = setting
        self.message = f"Missing configuration setting - {setting}!"
        super().__init__(self.message)


class CloudVisionDataSource(DataSource, Job):  # pylint: disable=abstract-method
    """CloudVision SSoT Data Source."""

    source = ObjectVar(
        model=ExternalIntegration,
        queryset=ExternalIntegration.objects.all(),
        display_field="display",
        label="Arista CloudVision External Integration",
        description="ExternalIntegration containing information for connecting to Arista CloudVision",
    )
    debug = BooleanVar(description="Enable for more verbose debug logging")

    class Meta:
        """Meta data for DataSource."""

        name = "CloudVision ⟹ Nautobot"
        data_source = "Cloudvision"
        data_source_icon = static("nautobot_ssot_aristacv/cvp_logo.png")
        description = "Sync system tag data from CloudVision to Nautobot"

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        if APP_SETTINGS.get("aristacv_cvp_host"):
            server_type = "On prem"
            host = APP_SETTINGS.get("aristacv_cvp_host")
        else:
            server_type = "CVaaS"
            host = APP_SETTINGS.get("aristacv_cvaas_url")
        return {
            "Server type": server_type,
            "CloudVision host": host,
            "Username": APP_SETTINGS.get("aristacv_cvp_user"),
            "Verify": str(APP_SETTINGS.get("aristacv_verify")),
            "Delete devices on sync": APP_SETTINGS.get(
                "aristacv_delete_devices_on_sync", str(nautobot.DEFAULT_DELETE_DEVICES_ON_SYNC)
            ),
            "New device default site": APP_SETTINGS.get(
                "aristacv_from_cloudvision_default_site", nautobot.DEFAULT_SITE
            ),
            "New device default role": APP_SETTINGS.get(
                "aristacv_from_cloudvision_default_device_role", nautobot.DEFAULT_DEVICE_ROLE
            ),
            "New device default role color": APP_SETTINGS.get(
                "aristacv_from_cloudvision_default_device_role_color", nautobot.DEFAULT_DEVICE_ROLE_COLOR
            ),
            "Apply import tag": str(APP_SETTINGS.get("aristacv_apply_import_tag", nautobot.APPLY_IMPORT_TAG)),
            "Import Active": str(APP_SETTINGS.get("aristacv_import_active", "True")),
            # Password and Token are intentionally omitted!
        }

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping("topology_network_type", None, "Topology Network Type", None),
            DataMapping("mlag", None, "MLAG", None),
            DataMapping("mpls", None, "mpls", None),
            DataMapping("model", None, "Device Type", reverse(get_route_for_model(DeviceType, "list"))),
            DataMapping("systype", None, "systype", None),
            DataMapping("serialnumber", None, "Device Serial Number", None),
            DataMapping("pimbidir", None, "pimbidir", None),
            DataMapping("sflow", None, "sFlow", None),
            DataMapping("eostrain", None, "eostrain", None),
            DataMapping("tapagg", None, "tapagg", None),
            DataMapping("pim", None, "pim", None),
            DataMapping("bgp", None, "bgp", None),
            DataMapping("terminattr", None, "TerminAttr Version", None),
            DataMapping("ztp", None, "ztp", None),
            DataMapping("eos", None, "EOS Version", None),
            DataMapping("topology_type", None, "Topology Type", None),
        )

    def load_source_adapter(self):
        """Load data from CloudVision into DiffSync models."""
        if not self.source_settings["from_cloudvision_default_site"]:
            self.logger.error(
                "App setting `from_cloudvision_default_site` is not defined. This setting is required for the App to function."
            )
            raise MissingConfigSetting(setting="from_cloudvision_default_site")
        if not self.source_settings["from_cloudvision_default_device_role"]:
            self.logger.error(
                "App setting `from_cloudvision_default_device_role` is not defined. This setting is required for the App to function."
            )
            raise MissingConfigSetting(setting="from_cloudvision_default_device_role")
        if self.debug:
            if self.source_settings["delete_devices_on_sync"]:
                self.logger.warning(
                    "Devices not present in Cloudvision but present in Nautobot will be deleted from Nautobot."
                )
            else:
                self.logger.warning(
                    "Devices not present in Cloudvision but present in Nautobot will not be deleted from Nautobot."
                )
            self.logger.info("Connecting to CloudVision")
        with CloudvisionApi(
            cvp_host=self.source_settings["cvp_host"],
            cvp_port=self.source_settings["cvp_port"],
            verify=self.source_settings["verify"],
            username=self.source_settings["cvp_user"],
            password=self.source_settings["cvp_password"],
            cvp_token=self.source_settings["cvp_token"],
        ) as client:
            self.logger.info("Loading data from CloudVision")
            self.source_adapter = CloudvisionAdapter(job=self, conn=client)
            self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.logger.info("Loading data from Nautobot")
        self.target_adapter = NautobotAdapter(job=self)
        self.target_adapter.load()

    def run(  # pylint: disable=arguments-differ, too-many-arguments, duplicate-code
        self,
        source,
        dryrun,
        memory_profiling,
        debug,
        *args,
        **kwargs,
    ):
        """Perform data synchronization."""
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling

        try:
            self.source_settings = _get_settings(source)
        except Exception as exc:
            # TBD: Why is this exception swallowed?
            self.logger.error(exc)
            raise

        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


class CloudVisionDataTarget(DataTarget, Job):  # pylint: disable=abstract-method
    """CloudVision SSoT Data Target."""

    target = ObjectVar(
        model=ExternalIntegration,
        queryset=ExternalIntegration.objects.all(),
        display_field="display",
        label="Arista CloudVision External Integration",
        description="ExternalIntegration containing information for connecting to Arista CloudVision",
    )
    debug = BooleanVar(description="Enable for more verbose debug logging")

    class Meta:
        """Meta data for DataTarget."""

        name = "Nautobot ⟹ CloudVision"
        data_target = "CloudVision"
        data_target_icon = static("nautobot_ssot_aristacv/cvp_logo.png")
        description = "Sync tag data from Nautobot to CloudVision"

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataTarget."""
        if APP_SETTINGS.get("aristacv_cvp_host"):
            return {
                "Server type": "On prem",
                "CloudVision host": APP_SETTINGS.get("aristacv_cvp_host"),
                "Username": APP_SETTINGS.get("aristacv_cvp_user"),
                "Verify": str(APP_SETTINGS.get("aristacv_verify")),
                # Password is intentionally omitted!
            }
        return {
            "Server type": "CVaaS",
            "CloudVision host": APP_SETTINGS.get("aristacv_cvaas_url"),
            # Token is intentionally omitted!
        }

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataTarget."""
        return (DataMapping("Tags", reverse("extras:tag_list"), "Device Tags", None),)

    def load_source_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.logger.info("Loading data from Nautobot")
        self.source_adapter = NautobotAdapter(job=self)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from CloudVision into DiffSync models."""
        if self.debug:
            if self.target_settings["delete_devices_on_sync"]:
                self.logger.warning(
                    "Devices not present in Cloudvision but present in Nautobot will be deleted from Nautobot."
                )
            else:
                self.logger.warning(
                    "Devices not present in Cloudvision but present in Nautobot will not be deleted from Nautobot."
                )
            self.logger.info("Connecting to CloudVision")
        with CloudvisionApi(
            cvp_host=self.target_settings["cvp_host"],
            cvp_port=self.target_settings["cvp_port"],
            verify=self.target_settings["verify"],
            username=self.target_settings["cvp_user"],
            password=self.target_settings["cvp_password"],
            cvp_token=self.target_settings["cvp_token"],
        ) as client:
            self.logger.info("Loading data from CloudVision")
            self.target_adapter = CloudvisionAdapter(job=self, conn=client)
            self.target_adapter.load()

    def run(  # pylint: disable=arguments-differ, too-many-arguments, duplicate-code
        self,
        target,
        dryrun,
        memory_profiling,
        debug,
        *args,
        **kwargs,
    ):
        """Perform data synchronization."""
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling

        try:
            self.target_settings = _get_settings(target)
        except Exception as exc:
            # TBD: Why is this exception swallowed?
            self.logger.error(exc)
            raise

        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [CloudVisionDataSource, CloudVisionDataTarget]
