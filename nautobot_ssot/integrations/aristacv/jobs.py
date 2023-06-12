# pylint: disable=invalid-name,too-few-public-methods
"""Jobs for CloudVision integration with SSoT plugin."""
from django.templatetags.static import static
from django.urls import reverse

from nautobot.dcim.models import DeviceType
from nautobot.extras.jobs import Job, BooleanVar
from nautobot.utilities.utils import get_route_for_model
from nautobot_ssot.jobs.base import DataTarget, DataSource, DataMapping

from nautobot_ssot.integrations.aristacv.constant import APP_SETTINGS
from nautobot_ssot.integrations.aristacv.diffsync.adapters.cloudvision import CloudvisionAdapter
from nautobot_ssot.integrations.aristacv.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.integrations.aristacv.diffsync.models import nautobot
from nautobot_ssot.integrations.aristacv.utils.cloudvision import CloudvisionApi


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
        if APP_SETTINGS.get("cvp_host"):
            server_type = "On prem"
            host = APP_SETTINGS.get("cvp_host")
        else:
            server_type = "CVaaS"
            host = APP_SETTINGS.get("cvaas_url")
        return {
            "Server type": server_type,
            "CloudVision host": host,
            "Username": APP_SETTINGS.get("cvp_user"),
            "Verify": str(APP_SETTINGS.get("verify")),
            "Delete devices on sync": APP_SETTINGS.get(
                "delete_devices_on_sync", str(nautobot.DEFAULT_DELETE_DEVICES_ON_SYNC)
            ),
            "New device default site": APP_SETTINGS.get("from_cloudvision_default_site", nautobot.DEFAULT_SITE),
            "New device default role": APP_SETTINGS.get(
                "from_cloudvision_default_device_role", nautobot.DEFAULT_DEVICE_ROLE
            ),
            "New device default role color": APP_SETTINGS.get(
                "from_cloudvision_default_device_role_color", nautobot.DEFAULT_DEVICE_ROLE_COLOR
            ),
            "Apply import tag": str(APP_SETTINGS.get("apply_import_tag", nautobot.APPLY_IMPORT_TAG)),
            "Import Active": str(APP_SETTINGS.get("import_active", "True"))
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
        if self.kwargs.get("debug"):
            if APP_SETTINGS.get("delete_devices_on_sync"):
                self.log_warning(
                    message="Devices not present in Cloudvision but present in Nautobot will be deleted from Nautobot."
                )
            else:
                self.log_warning(
                    message="Devices not present in Cloudvision but present in Nautobot will not be deleted from Nautobot."
                )
            self.log("Connecting to CloudVision")
        with CloudvisionApi(
            cvp_host=APP_SETTINGS["cvp_host"],
            cvp_port=APP_SETTINGS.get("cvp_port", "8443"),
            verify=APP_SETTINGS["verify"],
            username=APP_SETTINGS["cvp_user"],
            password=APP_SETTINGS["cvp_password"],
            cvp_token=APP_SETTINGS["cvp_token"],
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
        if APP_SETTINGS.get("cvp_host"):
            return {
                "Server type": "On prem",
                "CloudVision host": APP_SETTINGS.get("cvp_host"),
                "Username": APP_SETTINGS.get("cvp_user"),
                "Verify": str(APP_SETTINGS.get("verify"))
                # Password is intentionally omitted!
            }
        return {
            "Server type": "CVaaS",
            "CloudVision host": APP_SETTINGS.get("cvaas_url"),
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
        if self.kwargs.get("debug"):
            if APP_SETTINGS.get("delete_devices_on_sync"):
                self.log_warning(
                    message="Devices not present in Cloudvision but present in Nautobot will be deleted from Nautobot."
                )
            else:
                self.log_warning(
                    message="Devices not present in Cloudvision but present in Nautobot will not be deleted from Nautobot."
                )
            self.log("Connecting to CloudVision")
        with CloudvisionApi(
            cvp_host=APP_SETTINGS["cvp_host"],
            cvp_port=APP_SETTINGS.get("cvp_port", "8443"),
            verify=APP_SETTINGS["verify"],
            username=APP_SETTINGS["cvp_user"],
            password=APP_SETTINGS["cvp_password"],
            cvp_token=APP_SETTINGS["cvp_token"],
        ) as client:
            self.log("Loading data from CloudVision")
            self.target_adapter = CloudvisionAdapter(job=self, conn=client)
            self.target_adapter.load()


jobs = [CloudVisionDataSource, CloudVisionDataTarget]
