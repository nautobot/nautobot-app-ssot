# pylint: disable=invalid-name,too-few-public-methods
"""Jobs for CloudVision integration with SSoT app."""

from django.templatetags.static import static
from django.urls import reverse
from nautobot.core.utils.lookup import get_route_for_model
from nautobot.dcim.models import DeviceType
from nautobot.extras.jobs import BooleanVar
from nautobot.extras.jobs import Job
from nautobot_ssot.integrations.aristacv.diffsync.adapters.cloudvision import CloudvisionAdapter
from nautobot_ssot.integrations.aristacv.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.integrations.aristacv.utils.cloudvision import CloudvisionApi
from nautobot_ssot.integrations.aristacv.utils.nautobot import get_config
from nautobot_ssot.jobs.base import DataMapping
from nautobot_ssot.jobs.base import DataSource
from nautobot_ssot.jobs.base import DataTarget

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
        data_source = "CloudVision"
        data_source_icon = static("nautobot_ssot_aristacv/cvp_logo.png")
        description = "Sync system tag data from CloudVision to Nautobot"

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        config = get_config()

        return {
            "Server Type": "On prem" if config.is_on_premise else "CVaaS",
            "CloudVision URL": config.url,
            "User Name": config.cvp_user,
            "Verify SSL": str(config.verify_ssl),
            "Delete Devices On Sync": config.delete_devices_on_sync,
            "New Device Default Site": config.from_cloudvision_default_site,
            "New Device Default Role": config.from_cloudvision_default_device_role,
            "New Device Default Role Color": config.from_cloudvision_default_device_role_color,
            "Apply Import Tag": str(config.apply_import_tag),
            "Import Active": str(config.import_active),
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

    def __init__(self, *args, **kwargs):
        """Initialize the CloudVision Data Target."""
        super().__init__(*args, **kwargs)
        self.app_config = get_config()

    def load_source_adapter(self):
        """Load data from CloudVision into DiffSync models."""
        if not self.app_config.from_cloudvision_default_site:
            self.logger.error(
                "App setting `from_cloudvision_default_site` is not defined. This setting is required for the App to function."
            )
            raise MissingConfigSetting(setting="from_cloudvision_default_site")
        if not self.app_config.from_cloudvision_default_device_role:
            self.logger.error(
                "App setting `from_cloudvision_default_device_role` is not defined. This setting is required for the App to function."
            )
            raise MissingConfigSetting(setting="from_cloudvision_default_device_role")
        if self.debug:
            if self.app_config.delete_devices_on_sync:
                self.logger.warning(
                    "Devices not present in CloudVision but present in Nautobot will be deleted from Nautobot."
                )
            else:
                self.logger.warning(
                    "Devices not present in CloudVision but present in Nautobot will not be deleted from Nautobot."
                )
            self.logger.info("Connecting to CloudVision")
        with CloudvisionApi(self.app_config) as client:
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
        config = get_config()

        if config.is_on_premise:
            return {
                "Server Type": "On prem",
                "CloudVision URL": config.url,
                "Verify": str(config.verify_ssl),
                "User Name": config.cvp_user,
                # Password is intentionally omitted!
            }
        return {
            "Server Type": "CVaaS",
            "CloudVision URL": config.url,
            # Token is intentionally omitted!
        }

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataTarget."""
        return (DataMapping("Tags", reverse("extras:tag_list"), "Device Tags", None),)

    def __init__(self, *args, **kwargs):
        """Initialize the CloudVision Data Target."""
        super().__init__(*args, **kwargs)
        self.app_config = get_config()

    def load_source_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.logger.info("Loading data from Nautobot")
        self.source_adapter = NautobotAdapter(job=self)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from CloudVision into DiffSync models."""
        if self.debug:
            if self.app_config.delete_devices_on_sync:
                self.logger.warning(
                    "Devices not present in CloudVision but present in Nautobot will be deleted from Nautobot."
                )
            else:
                self.logger.warning(
                    "Devices not present in CloudVision but present in Nautobot will not be deleted from Nautobot."
                )
            self.logger.info("Connecting to CloudVision")
        with CloudvisionApi(self.app_config) as client:
            self.logger.info("Loading data from CloudVision")
            self.target_adapter = CloudvisionAdapter(job=self, conn=client)
            self.target_adapter.load()

    def run(  # pylint: disable=arguments-differ, too-many-arguments, duplicate-code
        self,
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

        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [CloudVisionDataSource, CloudVisionDataTarget]
