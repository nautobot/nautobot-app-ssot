"""ServiceNow Data Target Job."""

from django.core.exceptions import ObjectDoesNotExist
from django.templatetags.static import static
from django.urls import reverse

from nautobot.dcim.models import Device, DeviceType, Interface, Manufacturer, Location
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

    delete_records = BooleanVar(description="Delete synced records from ServiceNow if not present in Nautobot")

    site_filter = ObjectVar(
        description="Only sync records belonging to a single Site.",
        model=Location,
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
            DataMapping("Location", reverse("dcim:location_list"), "Location", None),
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

    def load_source_adapter(self):
        """Load Nautobot adapter."""
        self.logger.info("Loading current data from Nautobot...")
        self.source_adapter = NautobotDiffSync(job=self, sync=self.sync, site_filter=self.site_filter)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load ServiceNow adapter."""
        configs = get_servicenow_parameters()
        snc = ServiceNowClient(
            instance=configs.get("instance"),
            username=configs.get("username"),
            password=configs.get("password"),
            worker=self,
        )

        self.logger.info("Loading current data from ServiceNow...")
        self.target_adapter = ServiceNowDiffSync(client=snc, job=self, sync=self.sync, site_filter=self.site_filter)
        self.target_adapter.load()

    def run(self, dryrun, memory_profiling, site_filter, *args, **kwargs):  # pylint:disable=arguments-differ
        """Run sync."""
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        self.site_filter = site_filter
        super().run(dryrun, memory_profiling, *args, **kwargs)

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
                obj = Location.objects.get(name=unique_id)
            elif model_name == "product_model":
                manufacturer, model, _ = unique_id.split("__")
                obj = DeviceType.objects.get(manufacturer__name=manufacturer, model=model)
        except ObjectDoesNotExist:
            pass
        return obj


jobs = [ServiceNowDataTarget]
