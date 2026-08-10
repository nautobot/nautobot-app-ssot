"""Jobs for Panorama SSoT integration."""

from diffsync import DiffSyncFlags
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from nautobot.apps.jobs import BooleanVar, MultiObjectVar, ObjectVar
from nautobot.dcim.models import Controller, Device, Platform
from nautobot.extras.models import MetadataType, ObjectMetadata, Role, Status

from nautobot_ssot.exceptions import ConfigurationError
from nautobot_ssot.integrations.panorama.constants import (
    DEFAULT_FIREWALL_ROLE_NAME,
    FIREWALL_MANUFACTURER_NAME,
    FIREWALL_NETWORK_DRIVER,
)
from nautobot_ssot.integrations.panorama.diffsync.adapters import nautobot, panorama
from nautobot_ssot.jobs.base import DataMapping, DataSource

name = "Panorama SSoT"  # pylint: disable=invalid-name


class PanoramaDataSource(DataSource):  # pylint: disable=too-many-instance-attributes
    """Panorama SSoT Data Source."""

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
        query_params={"manufacturer": FIREWALL_MANUFACTURER_NAME},
        description="Device(s) to sync. If not specified, all devices from the controller will be synced.",
    )

    def __init__(self):
        """Initialize Panorama Data Source."""
        super().__init__()
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE
        self.loaded_panorama_devices = set()
        self.loaded_panorama_device_types = set()
        self.filtered_device_serials = None
        self.firewall_platform = None
        self.firewall_role = None

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
            DataMapping(
                "Device Group",
                None,
                "Controller Managed Device Group",
                reverse("dcim:controllermanageddevicegroup_list"),
            ),
            DataMapping("VSYS", None, "Virtual Device Context", reverse("dcim:virtualdevicecontext_list")),
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

        platforms = list(Platform.objects.filter(network_driver=FIREWALL_NETWORK_DRIVER).order_by("name"))
        if not platforms:
            raise ConfigurationError(
                f"No platform uses network driver '{FIREWALL_NETWORK_DRIVER}'. Run "
                "'nautobot-server post_upgrade' to create one, or set that network driver on the "
                "platform your Palo Alto firewalls already use."
            )
        if len(platforms) > 1:
            raise ConfigurationError(
                f"{len(platforms)} platforms use network driver '{FIREWALL_NETWORK_DRIVER}': "
                f"{', '.join(platform.name for platform in platforms)}. Devices split across them would "
                "resync their software version assignment on every run. Remove the driver from, or "
                "delete, the platforms you do not want."
            )
        self.firewall_platform = platforms[0]
        manufacturer = self.firewall_platform.manufacturer
        if manufacturer and manufacturer.name != FIREWALL_MANUFACTURER_NAME:
            raise ConfigurationError(
                f"Platform '{self.firewall_platform.name}' is assigned to manufacturer "
                f"'{manufacturer.name}', but this integration creates Palo Alto device types under "
                f"'{FIREWALL_MANUFACTURER_NAME}'. Reassign this platform to "
                f"'{FIREWALL_MANUFACTURER_NAME}' and run the job again."
            )

        role_name = settings.PLUGINS_CONFIG["nautobot_ssot"].get(
            "panorama_firewall_role_name", DEFAULT_FIREWALL_ROLE_NAME
        )
        self.firewall_role, _ = Role.objects.get_or_create(name=role_name)
        self.firewall_role.content_types.add(ContentType.objects.get_for_model(Device))

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
