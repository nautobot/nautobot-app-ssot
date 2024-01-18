# pylint: disable=invalid-name,too-few-public-methods
"""Jobs for CloudVision integration with SSoT app."""
from django.templatetags.static import static
from django.urls import reverse

from nautobot.dcim.models import DeviceType
from nautobot.extras.jobs import Job, BooleanVar
from nautobot.core.utils.lookup import get_route_for_model
from nautobot_ssot.jobs.base import DataTarget, DataSource, DataMapping

from nautobot_ssot.integrations.aristacv.constant import APP_SETTINGS
from nautobot_ssot.integrations.aristacv.diffsync.adapters.cloudvision import CloudvisionAdapter
from nautobot_ssot.integrations.aristacv.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.integrations.aristacv.diffsync.models import nautobot
from nautobot_ssot.integrations.aristacv.utils.cloudvision import CloudvisionApi


name = "SSoT - Arista CloudVision"  # pylint: disable=invalid-name


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
            "Import Active": str(APP_SETTINGS.get("aristacv_import_active", "True"))
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
        if not APP_SETTINGS.get("aristacv_from_cloudvision_default_site"):
            self.logger.error(
                "App setting `aristacv_from_cloudvision_default_site` is not defined. This setting is required for the App to function."
            )
            raise MissingConfigSetting(setting="aristacv_from_cloudvision_default_site")
        if not APP_SETTINGS.get("aristacv_from_cloudvision_default_device_role"):
            self.logger.error(
                "App setting `aristacv_from_cloudvision_default_device_role` is not defined. This setting is required for the App to function."
            )
            raise MissingConfigSetting(setting="aristacv_from_cloudvision_default_device_role")
        if self.debug:
            if APP_SETTINGS.get("aristacv_delete_devices_on_sync"):
                self.logger.warning(
                    "Devices not present in Cloudvision but present in Nautobot will be deleted from Nautobot."
                )
            else:
                self.logger.warning(
                    "Devices not present in Cloudvision but present in Nautobot will not be deleted from Nautobot."
                )
            self.logger.info("Connecting to CloudVision")
        with CloudvisionApi(
            cvp_host=APP_SETTINGS["aristacv_cvp_host"],
            cvp_port=APP_SETTINGS.get("aristacv_cvp_port", "8443"),
            verify=APP_SETTINGS["aristacv_verify"],
            username=APP_SETTINGS["aristacv_cvp_user"],
            password=APP_SETTINGS["aristacv_cvp_password"],
            cvp_token=APP_SETTINGS["aristacv_cvp_token"],
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
        self, dryrun, memory_profiling, debug, *args, **kwargs
    ):
        """Perform data synchronization."""
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


class CloudVisionDataTarget(DataTarget, Job):  # pylint: disable=abstract-method
    """CloudVision SSoT Data Target."""

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
                "Verify": str(APP_SETTINGS.get("aristacv_verify"))
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
            if APP_SETTINGS.get("aristacv_delete_devices_on_sync"):
                self.logger.warning(
                    "Devices not present in Cloudvision but present in Nautobot will be deleted from Nautobot."
                )
            else:
                self.logger.warning(
                    "Devices not present in Cloudvision but present in Nautobot will not be deleted from Nautobot."
                )
            self.logger.info("Connecting to CloudVision")
        with CloudvisionApi(
            cvp_host=APP_SETTINGS["aristacv_cvp_host"],
            cvp_port=APP_SETTINGS.get("aristacv_cvp_port", "8443"),
            verify=APP_SETTINGS["aristacv_verify"],
            username=APP_SETTINGS["aristacv_cvp_user"],
            password=APP_SETTINGS["aristacv_cvp_password"],
            cvp_token=APP_SETTINGS["aristacv_cvp_token"],
        ) as client:
            self.logger.info("Loading data from CloudVision")
            self.target_adapter = CloudvisionAdapter(job=self, conn=client)
            self.target_adapter.load()

    def run(  # pylint: disable=arguments-differ, too-many-arguments, duplicate-code
        self, dryrun, memory_profiling, debug, *args, **kwargs
    ):
        """Perform data synchronization."""
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [CloudVisionDataSource, CloudVisionDataTarget]
