"""ServiceNow Data Target Job."""
from django.core.exceptions import ObjectDoesNotExist
from django.templatetags.static import static
from django.urls import reverse

from diffsync.enum import DiffSyncFlags

from nautobot.dcim.models import Device, DeviceType, Interface, Manufacturer, Region, Site
from nautobot.extras.jobs import Job, BooleanVar, ObjectVar

from nautobot_ssot.jobs.base import DataMapping, DataTarget

from .diffsync.adapter_nautobot import NautobotDiffSync
from .diffsync.adapter_servicenow import ServiceNowDiffSync
from .servicenow import ServiceNowClient
from .utils import get_servicenow_parameters


name = "SSoT - ServiceNow"  # pylint: disable=invalid-name


class ServiceNowDataTarget(DataTarget, Job):  # pylint: disable=abstract-method
    """Job syncing data from Nautobot to ServiceNow."""

    debug = BooleanVar(description="Enable for more verbose logging.")

    log_unchanged = BooleanVar(
        description="Create log entries even for unchanged objects",
        default=False,
    )

    # TODO: not yet implemented
    # delete_records = BooleanVar(
    #     description="Delete records from ServiceNow if not present in Nautobot",
    #     default=False,
    # )

    site_filter = ObjectVar(
        description="Only sync records belonging to a single Site.",
        model=Site,
        default=None,
        required=False,
    )

    class Meta:
        """Metadata about this Job."""

        name = "Nautobot ⟹ ServiceNow"
        data_target = "ServiceNow"
        data_target_icon = static("nautobot_ssot_servicenow/ServiceNow_logo.svg")
        description = "Synchronize data from Nautobot into ServiceNow."

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataTarget."""
        return (
            DataMapping("Device", reverse("dcim:device_list"), "IP Switch", None),
            DataMapping("Device Type", reverse("dcim:devicetype_list"), "Hardware Product Model", None),
            DataMapping("Interface", reverse("dcim:interface_list"), "Interface", None),
            DataMapping("Manufacturer", reverse("dcim:manufacturer_list"), "Company", None),
            DataMapping("Region", reverse("dcim:region_list"), "Location", None),
            DataMapping("Site", reverse("dcim:site_list"), "Location", None),
        )

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataTarget."""
        configs = get_servicenow_parameters()
        return {
            "ServiceNow instance": configs.get("instance"),
            "Username": configs.get("username"),
            # Password is intentionally omitted!
        }

    def sync_data(self):
        """Sync a slew of Nautobot data into ServiceNow."""
        configs = get_servicenow_parameters()
        snc = ServiceNowClient(
            instance=configs.get("instance"),
            username=configs.get("username"),
            password=configs.get("password"),
            worker=self,
        )

        self.log_info(message="Loading current data from ServiceNow...")
        servicenow_diffsync = ServiceNowDiffSync(
            client=snc, job=self, sync=self.sync, site_filter=self.kwargs.get("site_filter")
        )
        servicenow_diffsync.load()

        self.log_info(message="Loading current data from Nautobot...")
        nautobot_diffsync = NautobotDiffSync(job=self, sync=self.sync, site_filter=self.kwargs.get("site_filter"))
        nautobot_diffsync.load()

        diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE
        if self.kwargs.get("log_unchanged"):
            diffsync_flags |= DiffSyncFlags.LOG_UNCHANGED_RECORDS
        if not self.kwargs.get("delete_records"):
            diffsync_flags |= DiffSyncFlags.SKIP_UNMATCHED_DST

        self.log_info(message="Calculating diffs...")
        diff = servicenow_diffsync.diff_from(nautobot_diffsync, flags=diffsync_flags)
        self.sync.diff = diff.dict()
        self.sync.save()

        if not self.kwargs["dry_run"]:
            self.log_info(message="Syncing from Nautobot to ServiceNow...")
            servicenow_diffsync.sync_from(nautobot_diffsync, flags=diffsync_flags)
            self.log_info(message="Sync complete")

    def log_debug(self, message):
        """Conditionally log a debug message."""
        if self.kwargs.get("debug"):
            super().log_debug(message)

    def lookup_object(self, model_name, unique_id):
        """Look up a Nautobot object based on the DiffSync model name and unique ID."""
        obj = None
        try:
            if model_name == "company":
                obj = Manufacturer.objects.get(name=unique_id)
            elif model_name == "device":
                obj = Device.objects.get(name=unique_id)
            elif model_name == "interface":
                device_name, interface_name = unique_id.split("__")
                obj = Interface.objects.get(device__name=device_name, name=interface_name)
            elif model_name == "location":
                try:
                    obj = Site.objects.get(name=unique_id)
                except Site.DoesNotExist:
                    obj = Region.objects.get(name=unique_id)
            elif model_name == "product_model":
                manufacturer, model, _ = unique_id.split("__")
                obj = DeviceType.objects.get(manufacturer__name=manufacturer, model=model)
        except ObjectDoesNotExist:
            pass
        return obj


jobs = [ServiceNowDataTarget]
