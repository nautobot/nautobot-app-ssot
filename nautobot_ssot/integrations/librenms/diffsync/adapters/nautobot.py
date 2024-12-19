"""Nautobot Adapter for LibreNMS SSoT app."""

from diffsync import DiffSync
from diffsync.enum import DiffSyncModelFlags
from diffsync.exceptions import ObjectNotFound
from nautobot.dcim.models import Device as OrmDevice
from nautobot.dcim.models import Location as OrmLocation

from nautobot_ssot.integrations.librenms.diffsync.models.nautobot import (
    NautobotDevice,
    NautobotLocation,
)
from nautobot_ssot.integrations.librenms.utils import check_sor_field, get_sor_field_nautobot_object


class NautobotAdapter(DiffSync):
    """DiffSync adapter for Nautobot."""

    location = NautobotLocation
    device = NautobotDevice

    top_level = ["location", "device"]

    def __init__(self, *args, job=None, sync=None, **kwargs):
        """Initialize Nautobot.

        Args:
            job (object, optional): Nautobot job. Defaults to None.
            sync (object, optional): Nautobot DiffSync. Defaults to None.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync

    def load_location(self):
        """Load Location objects from Nautobot into DiffSync Models."""
        if self.job.tenant:
            locations = OrmLocation.objects.filter(tenant=self.job.tenant)
        else:
            locations = OrmLocation.objects.all()
        for nb_location in locations:
            self.job.logger.debug(f"Loading Nautobot Location {nb_location}")
            try:
                self.get(self.location, nb_location.name)
            except ObjectNotFound:
                _parent = None
                if nb_location.parent is not None:
                    _parent = nb_location.parent.name
                new_location = NautobotLocation(
                    name=nb_location.name,
                    location_type=nb_location.location_type.name,
                    parent=_parent,
                    latitude=nb_location.latitude,
                    longitude=nb_location.longitude,
                    status=nb_location.status.name,
                    system_of_record=get_sor_field_nautobot_object(nb_location),
                    uuid=nb_location.id,
                )
                if not check_sor_field(nb_location):
                    new_location.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_location)

    def load_device(self):
        """Load Device objects from Nautobot into DiffSync models."""
        if self.job.tenant:
            devices = OrmDevice.objects.filter(tenant=self.job.tenant)
        else:
            devices = OrmDevice.objects.all()
        for nb_device in devices:
            self.job.logger.debug(f"Loading Nautobot Device {nb_device}")
            try:
                self.get(self.device, nb_device.name)
            except ObjectNotFound:
                try:
                    _software_version = nb_device.software_version.version
                except AttributeError:
                    _software_version = None
                _device_id = None
                if nb_device.custom_field_data.get("librenms_device_id"):
                    _device_id = nb_device.custom_field_data.get("librenms_device_id")
                new_device = NautobotDevice(
                    name=nb_device.name,
                    device_id=_device_id,
                    location=nb_device.location.name,
                    status=nb_device.status.name,
                    device_type=nb_device.device_type.display.split(f"{nb_device.platform.manufacturer.name}", 1)[
                        1
                    ].strip(),
                    role=nb_device.role.name,
                    manufacturer=nb_device.platform.manufacturer.name,
                    platform=nb_device.platform.name,
                    os_version=_software_version,
                    serial_no=nb_device.serial,
                    system_of_record=get_sor_field_nautobot_object(nb_device),
                    uuid=nb_device.id,
                )
                if not check_sor_field(nb_device):
                    new_device.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_device)

    def load(self):
        """Load data from Nautobot into DiffSync models."""
        if self.job.sync_locations:
            if self.job.debug:
                self.job.logger.debug("Loading Nautobot Locations")
            self.load_location()

        if self.job.debug:
            self.job.logger.debug("Loading Nautobot Devices")
        self.load_device()
