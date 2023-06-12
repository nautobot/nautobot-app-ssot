# pylint: disable=invalid-name,too-few-public-methods
"""Jobs for CloudVision integration with SSoT plugin."""
from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse

from nautobot.dcim.models import DeviceType
from nautobot.extras.jobs import Job, BooleanVar
from nautobot.utilities.utils import get_route_for_model
from nautobot_ssot.jobs.base import DataTarget, DataSource, DataMapping

from nautobot_ssot_aristacv.diffsync.adapters.cloudvision import CloudvisionAdapter
from nautobot_ssot_aristacv.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot_aristacv.diffsync.models import nautobot
from nautobot_ssot_aristacv.utils.cloudvision import CloudvisionApi


name = "SSoT - Arista CloudVision"  # pylint: disable=invalid-name


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
        PLUGIN_SETTINGS = settings.PLUGINS_CONFIG["nautobot_ssot_aristacv"]
        if PLUGIN_SETTINGS.get("cvp_host"):
            server_type = "On prem"
            host = PLUGIN_SETTINGS.get("cvp_host")
        else:
            server_type = "CVaaS"
            host = PLUGIN_SETTINGS.get("cvaas_url")
        return {
            "Server type": server_type,
            "CloudVision host": host,
            "Username": PLUGIN_SETTINGS.get("cvp_user"),
            "Verify": str(PLUGIN_SETTINGS.get("verify")),
            "Delete devices on sync": PLUGIN_SETTINGS.get(
                "delete_devices_on_sync", str(nautobot.DEFAULT_DELETE_DEVICES_ON_SYNC)
            ),
            "New device default site": PLUGIN_SETTINGS.get("from_cloudvision_default_site", nautobot.DEFAULT_SITE),
            "New device default role": PLUGIN_SETTINGS.get(
                "from_cloudvision_default_device_role", nautobot.DEFAULT_DEVICE_ROLE
            ),
            "New device default role color": PLUGIN_SETTINGS.get(
                "from_cloudvision_default_device_role_color", nautobot.DEFAULT_DEVICE_ROLE_COLOR
            ),
            "Apply import tag": str(PLUGIN_SETTINGS.get("apply_import_tag", nautobot.APPLY_IMPORT_TAG)),
            "Import Active": str(PLUGIN_SETTINGS.get("import_active", "True"))
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
        PLUGIN_SETTINGS = settings.PLUGINS_CONFIG["nautobot_ssot_aristacv"]
        if self.kwargs.get("debug"):
            if PLUGIN_SETTINGS.get("delete_devices_on_sync"):
                self.log_warning(
                    message="Devices not present in Cloudvision but present in Nautobot will be deleted from Nautobot."
                )
            else:
                self.log_warning(
                    message="Devices not present in Cloudvision but present in Nautobot will not be deleted from Nautobot."
                )
            self.log("Connecting to CloudVision")
        with CloudvisionApi(
            cvp_host=PLUGIN_SETTINGS["cvp_host"],
            cvp_port=PLUGIN_SETTINGS.get("cvp_port", "8443"),
            verify=PLUGIN_SETTINGS["verify"],
            username=PLUGIN_SETTINGS["cvp_user"],
            password=PLUGIN_SETTINGS["cvp_password"],
            cvp_token=PLUGIN_SETTINGS["cvp_token"],
        ) as client:
            self.log("Loading data from CloudVision")
            self.source_adapter = CloudvisionAdapter(job=self, conn=client)
            self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.log("Loading data from Nautobot")
        self.target_adapter = NautobotAdapter(job=self)
        self.target_adapter.load()


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
        PLUGIN_SETTINGS = settings.PLUGINS_CONFIG["nautobot_ssot_aristacv"]
        if PLUGIN_SETTINGS.get("cvp_host"):
            return {
                "Server type": "On prem",
                "CloudVision host": PLUGIN_SETTINGS.get("cvp_host"),
                "Username": PLUGIN_SETTINGS.get("cvp_user"),
                "Verify": str(PLUGIN_SETTINGS.get("verify"))
                # Password is intentionally omitted!
            }
        return {
            "Server type": "CVaaS",
            "CloudVision host": PLUGIN_SETTINGS.get("cvaas_url"),
            # Token is intentionally omitted!
        }

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataTarget."""
        return (DataMapping("Tags", reverse("extras:tag_list"), "Device Tags", None),)

    def load_source_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.log("Loading data from Nautobot")
        self.source_adapter = NautobotAdapter(job=self)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from CloudVision into DiffSync models."""
        PLUGIN_SETTINGS = settings.PLUGINS_CONFIG["nautobot_ssot_aristacv"]
        if self.kwargs.get("debug"):
            if PLUGIN_SETTINGS.get("delete_devices_on_sync"):
                self.log_warning(
                    message="Devices not present in Cloudvision but present in Nautobot will be deleted from Nautobot."
                )
            else:
                self.log_warning(
                    message="Devices not present in Cloudvision but present in Nautobot will not be deleted from Nautobot."
                )
            self.log("Connecting to CloudVision")
        with CloudvisionApi(
            cvp_host=PLUGIN_SETTINGS["cvp_host"],
            cvp_port=PLUGIN_SETTINGS.get("cvp_port", "8443"),
            verify=PLUGIN_SETTINGS["verify"],
            username=PLUGIN_SETTINGS["cvp_user"],
            password=PLUGIN_SETTINGS["cvp_password"],
            cvp_token=PLUGIN_SETTINGS["cvp_token"],
        ) as client:
            self.log("Loading data from CloudVision")
            self.target_adapter = CloudvisionAdapter(job=self, conn=client)
            self.target_adapter.load()


jobs = [CloudVisionDataSource, CloudVisionDataTarget]
