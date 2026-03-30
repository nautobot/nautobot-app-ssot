"""Jobs for Panorama SSoT integration."""

from diffsync import DiffSyncFlags
from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from nautobot.apps.jobs import BooleanVar, MultiObjectVar, ObjectVar
from nautobot.dcim.models import Controller, Device
from nautobot.extras.models import MetadataType, ObjectMetadata, Status

from nautobot_ssot.integrations.panorama.diffsync.adapters import nautobot, panorama
from nautobot_ssot.jobs.base import DataMapping, DataSource

name = "Panorama SSoT"  # pylint: disable=invalid-name
app_settings = settings.PLUGINS_CONFIG.get("nautobot_ssot")


class PanoramaDataSource(DataSource):  # pylint: disable=too-many-instance-attributes
    """Panorama SSoT Data Source."""

    platform_name = app_settings.get("panorama_firewall_platform_name", "paloalto_panos")

    debug = BooleanVar(description="Enable for more verbose debug logging", default=False)
    panorama_controller = ObjectVar(model=Controller)
    default_device_status = ObjectVar(
        model=Status,
        query_params={"content_types": "dcim.device"},
        required=True,
        description="Status applied to all devices created during the sync.",
    )

    devices = MultiObjectVar(
        model=Device,
        required=False,
        query_params={"platform": platform_name},
        description="Device(s) to sync. If not specified, all devices from the controller will be synced.",
    )

    def __init__(self):
        """Initialize Panorama Data Source."""
        super().__init__()
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE
        # Used in the source adapter to load device data based on what was returned from panorama
        self.loaded_panorama_devices = set()
        # Optionally populated with device serials from devices selected in the job form.
        self.filtered_device_serials = None

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta data for Panorama."""

        name = "Panorama to Nautobot"
        data_source = "Panorama"
        data_target = "Nautobot"
        data_source_icon = static("nautobot_ssot_panorama/panorama.png")
        description = "Sync information from Panorama to Nautobot"
        has_sensitive_variables = False

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {}

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping("Device Group", None, "Logical Group", reverse("plugins:nautobot_ssot:logicalgroup_list")),
            DataMapping("VSYS", None, "Virtual System", reverse("plugins:nautobot_ssot:virtualsystem_list")),
            DataMapping("Firewall", None, "Device", reverse("dcim:device_list")),
            DataMapping(
                "Panorama",
                None,
                "Controller",
                reverse("dcim:controller_list"),
            ),
        )

    def load_source_adapter(self):
        """Load data from Panorama into DiffSync models."""
        self.source_adapter = panorama.PanoSSoTPanoramaAdapter(job=self, sync=self.sync, pan=self.panorama_controller)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.target_adapter = nautobot.PanoSSoTNautobotAdapter(job=self, sync=self.sync)
        self.target_adapter.load()

    def run(
        self,
        dryrun,
        debug,
        default_device_status,
        panorama_controller,
        devices,
        *args,
        **kwargs,
    ):  # pylint: disable=arguments-differ, too-many-arguments
        """Run the job."""
        self.debug = debug
        self.dryrun = dryrun
        self.default_device_status = default_device_status
        self.panorama_controller = panorama_controller
        self.devices = devices

        # Filter devices based on form input
        device_filter = {}
        if self.devices:
            device_filter["id__in"] = [device.id for device in self.devices]
        if device_filter:
            filtered_devices = Device.objects.filter(**device_filter)
            self.logger.info(f"{filtered_devices.count()} devices will be synced.")
            if filtered_devices.count() < 50:
                device_names = ", ".join([device.name for device in filtered_devices])
                self.logger.info("Devices to be synced: %s", device_names)
            self.filtered_device_serials = [device.serial for device in filtered_devices]
            # Stop the job if no devices are returned after filtering
            if not filtered_devices:
                self.logger.error("No devices match the job form filter, no devices will be processed.")
                return None
        return super().run(dryrun=self.dryrun, debug=self.debug, panorama=self.panorama_controller, *args, **kwargs)

    def on_success(self, retval, task_id, args, kwargs):
        """Update Firewall Metadata."""
        if not self.dryrun:
            self.logger.info("Updating metadata for Panorama devices.")
            for serial in self.loaded_panorama_devices:
                device = None
                try:
                    device = Device.objects.get(serial=serial)
                except ObjectDoesNotExist:
                    continue
                except MultipleObjectsReturned:
                    self.logger.error("Multiple devices found with serial %s, unable to update metadata.", serial)
                    continue
                try:
                    # Update last Panorama sync datetime Metadata
                    ################
                    # UPDATE THE BELOW TO USE METADATA UTILS ####
                    #################
                    metadata_type = MetadataType.objects.get(name="Last Panorama Sync")
                    try:
                        firewall_last_panorama_sync_metadata = ObjectMetadata.objects.get(
                            metadata_type=metadata_type, assigned_object_id=device.id
                        )
                    except ObjectDoesNotExist:
                        firewall_last_panorama_sync_metadata = ObjectMetadata(
                            metadata_type=metadata_type,
                            assigned_object=device,
                        )

                    scoped_fields = [
                        "name",
                        "platform",
                        "device_type",
                        "primary_ip4",
                        "software_version",
                    ]
                    firewall_last_panorama_sync_metadata.scoped_fields = scoped_fields
                    firewall_last_panorama_sync_metadata.value = timezone.now()
                    firewall_last_panorama_sync_metadata.validated_save()
                except Exception as err:  # pylint: disable=broad-exception-caught
                    self.logger.error(f"Unable to update metadata type for {device}, {err}")
        super().on_success(retval, task_id, args, kwargs)


jobs = [PanoramaDataSource]
#  register_jobs(*jobs)
