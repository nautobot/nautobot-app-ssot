"""Nautobot Adapter for LibreNMS SSoT app."""

from typing import Optional

from diffsync import Adapter
from diffsync.enum import DiffSyncModelFlags
from diffsync.exceptions import ObjectNotFound
from nautobot.dcim.models import Device as OrmDevice
from nautobot.dcim.models import Location as OrmLocation
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.librenms.constants import PLUGIN_CFG
from nautobot_ssot.integrations.librenms.diffsync.models.nautobot import (
    NautobotDevice,
    NautobotLocation,
)
from nautobot_ssot.integrations.librenms.utils import (
    check_sor_field,
    get_sor_field_nautobot_object,
)
from nautobot_ssot.integrations.librenms.utils.nautobot import (
    clear_network_driver_caches,
    platform_to_network_driver,
)


class NautobotAdapter(Adapter):
    """DiffSync adapter for Nautobot."""

    location = NautobotLocation
    device = NautobotDevice

    top_level = ["location", "device"]

    def __init__(self, *args, job=None, sync=None, tenant: Optional[Tenant] = None, **kwargs):
        """Initialize Nautobot.

        Args:
            job (object, optional): Nautobot job. Defaults to None.
            sync (object, optional): Nautobot DiffSync. Defaults to None.
        """
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        self.job = job
        self.sync = sync
        # Read once per sync so both adapters and ensure_platform agree within a run.
        self.consolidated_platforms = bool(PLUGIN_CFG.get("librenms_consolidated_platforms", False))

    def load_location(self):
        """Load Location objects from Nautobot into DiffSync Models."""
        if self.tenant:
            locations = OrmLocation.objects.filter(tenant=self.tenant)
        else:
            locations = OrmLocation.objects.all()
        for nb_location in locations:
            if self.job.debug:
                self.job.logger.debug(f"Nautobot Adapter Loading Nautobot Location {nb_location}")
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
        if self.tenant:
            devices = OrmDevice.objects.filter(tenant=self.tenant)
        else:
            devices = OrmDevice.objects.all()
        for nb_device in devices:
            if nb_device.platform is None:
                self.job.logger.warning(
                    f"Skipping device {nb_device.name}: no Platform assigned, cannot be synced with LibreNMS."
                )
                continue
            if self.job.debug:
                self.job.logger.debug(f"Nautobot Adapter Loading Nautobot Device {nb_device}")
                self.job.logger.debug(
                    f"Nautobot Adapter Platform for {nb_device.name}: {nb_device.platform.network_driver}"
                )
                self.job.logger.debug(
                    f"Nautobot Adapter Manufacturer for {nb_device.name}: {nb_device.device_type.manufacturer.name}"
                )
            try:
                self.get(self.device, nb_device.name)
            except ObjectNotFound:
                try:
                    _software_version = nb_device.software_version.version
                except AttributeError:
                    _software_version = None
                try:
                    _ip_address = str(nb_device.primary_ip4.address)
                    _ip_prefix = str(nb_device.primary_ip4.parent.prefix)
                except AttributeError:
                    _ip_address = None
                    _ip_prefix = None
                _device_id = None
                if nb_device.custom_field_data.get("librenms_device_id"):
                    _device_id = nb_device.custom_field_data.get("librenms_device_id")
                if nb_device.custom_field_data.get("snmp_location"):
                    _snmp_location = nb_device.custom_field_data.get("snmp_location")
                else:
                    _snmp_location = None
                new_device = NautobotDevice(
                    name=nb_device.name,
                    tenant=nb_device.tenant.name if nb_device.tenant else None,
                    device_id=_device_id,
                    location=nb_device.location.name,
                    parent_location=nb_device.location.parent.name if nb_device.location.parent else None,
                    status=nb_device.status.name,
                    device_type=nb_device.device_type.model,
                    role=nb_device.role.name,
                    manufacturer=nb_device.device_type.manufacturer.name,
                    platform=(
                        platform_to_network_driver(nb_device.platform)
                        if self.consolidated_platforms
                        else nb_device.platform.name
                    ),
                    os_version=_software_version,
                    serial_no=nb_device.serial,
                    ip_address=_ip_address,
                    ip_prefix=_ip_prefix,
                    snmp_location=_snmp_location,
                    system_of_record=get_sor_field_nautobot_object(nb_device),
                    uuid=nb_device.id,
                )
                if not check_sor_field(nb_device):
                    new_device.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

                self.add(new_device)

    def load(self):
        """Load data from Nautobot into DiffSync models."""
        # Keep driver resolution consistent with the LibreNMS side.
        clear_network_driver_caches()
        if self.job.sync_locations:
            if self.job.debug:
                self.job.logger.debug("Loading Nautobot Locations")
            self.load_location()

        if self.job.debug:
            self.job.logger.debug("Loading Nautobot Devices")
        self.load_device()
