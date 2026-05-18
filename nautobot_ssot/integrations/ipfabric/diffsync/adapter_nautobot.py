# pylint: disable=duplicate-code
# pylint: disable=too-many-arguments
# Load method is packed with conditionals  #  pylint: disable=too-many-branches
"""DiffSync adapter class for Nautobot as source-of-truth."""

import logging
from collections import defaultdict
from typing import Any, ClassVar, List, Optional

from diffsync import Adapter
from diffsync.exceptions import ObjectAlreadyExists
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError, Q
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import Device, Location
from nautobot.extras.models import Tag
from nautobot.ipam.models import VLAN, Interface
from netutils.ip import cidr_to_netmask
from netutils.mac import mac_to_format

import nautobot_ssot.integrations.ipfabric.utilities.nbutils as tonb_utils
from nautobot_ssot.integrations.ipfabric.constants import (
    DEFAULT_INTERFACE_MAC,
    DEFAULT_INTERFACE_MTU,
    SYNC_IPF_DEV_TYPE_TO_ROLE,
)
from nautobot_ssot.integrations.ipfabric.diffsync import DiffSyncModelAdapters

logger = logging.getLogger("nautobot.ssot.ipfabric")


class NautobotDiffSync(DiffSyncModelAdapters):
    """Nautobot adapter for DiffSync."""

    objects_to_delete = defaultdict(list)

    _vlan: ClassVar[Any] = VLAN
    _device: ClassVar[Any] = Device
    _location: ClassVar[Any] = Location
    _interface: ClassVar[Any] = Interface

    def __init__(
        self,
        job,
        sync,
        sync_ipfabric_tagged_only: bool,
        location_filter: Optional[Location],
        *args,
        **kwargs,
    ):
        """Initialize the NautobotDiffSync."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.sync_ipfabric_tagged_only = sync_ipfabric_tagged_only
        self.location_filter = location_filter
        self.ssot_tag = tonb_utils.get_or_create_tag_object(
            tag_name="SSoT Synced from IPFabric",
            tag_color=ColorChoices.COLOR_LIGHT_GREEN,
            description="Object synced at some point from IPFabric to Nautobot",
            app_label="dcim",
            model="device",
            logger=self.job.logger,
        )
        self.safe_delete_tag = tonb_utils.get_or_create_tag_object(
            tag_name="SSoT Safe Delete",
            tag_color=ColorChoices.COLOR_RED,
            description="Safe Delete Mode tag to flag an object, but not delete from Nautobot.",
            app_label="dcim",
            model="device",
            logger=self.job.logger,
        )

    def sync_complete(self, source: Adapter, *args, **kwargs):
        """Clean up function for DiffSync sync.

        Once the sync is complete, this function runs deleting any objects
        from Nautobot that need to be deleted in a specific order.

        Args:
            source (Adapter): DiffSync Adapter
        """
        for grouping in (
            "_vlan",
            "_interface",
            "_device",
            "_location",
        ):
            for nautobot_object in self.objects_to_delete[grouping]:
                if NautobotDiffSync.safe_delete_mode:
                    continue
                try:
                    nautobot_object.delete()
                except ProtectedError:
                    logger.warning("Deletion failed protected object", extra={"object": nautobot_object})
                except IntegrityError:
                    logger.warning(f"Deletion failed due to IntegrityError with {nautobot_object}")

            self.objects_to_delete[grouping] = []
        return super().sync_complete(source, *args, **kwargs)

    def load_interfaces(self, device_record: Device, diffsync_device):
        """Import a single Nautobot Interface object as a DiffSync Interface model."""
        device_primary_ip = None
        if device_record.primary_ip4:
            device_primary_ip = device_record.primary_ip4
        elif device_record.primary_ip6:
            device_primary_ip = device_record.primary_ip6

        for interface_record in device_record.interfaces.all():
            # Avoid .first() to preserve prefetch cache
            ip_addresses = interface_record.ip_addresses.all()
            if ip_addresses:
                ip_address_obj = ip_addresses[0]
                ip_address = ip_address_obj.host
                subnet_mask = cidr_to_netmask(ip_address_obj.mask_length)
            else:
                ip_address_obj = None
                ip_address = None
                subnet_mask = None
            interface = self.interface(
                status=device_record.status.name,
                name=interface_record.name,
                device_name=device_record.name,
                description=interface_record.description if interface_record.description else None,
                enabled=True,
                mac_address=(
                    mac_to_format(str(interface_record.mac_address), "MAC_COLON_TWO").upper()
                    if interface_record.mac_address
                    else DEFAULT_INTERFACE_MAC
                ),
                subnet_mask=subnet_mask,
                mtu=interface_record.mtu if interface_record.mtu else DEFAULT_INTERFACE_MTU,
                type=interface_record.type,
                mgmt_only=interface_record.mgmt_only if interface_record.mgmt_only else False,
                pk=interface_record.pk,
                ip_is_primary=ip_address_obj == device_primary_ip if device_primary_ip else False,
                ip_address=ip_address,
            )
            self.add(interface)
            diffsync_device.add_child(interface)

    def load_device(self, filtered_devices: List, location):
        """Load Devices from Nautobot."""
        optimized_query = (
            filtered_devices.select_related(
                "location",
                "device_type__manufacturer",
                "primary_ip4",
                "primary_ip6",
                "role",
                "status",
                "platform",
                "virtual_chassis",
                "virtual_chassis__master",
            )
            .prefetch_related("interfaces__ip_addresses")
            .iterator(1000)
        )
        for device_record in optimized_query:
            if self.job.debug:
                logger.debug("Loading Nautobot Device: %s", device_record.name)
            ipfabric_type = device_record.role.cf.get("ipfabric_type")
            device_role = str(ipfabric_type) if ipfabric_type else device_record.role.name
            device = self.device(
                name=device_record.name,
                model=str(device_record.device_type),
                role=device_role if SYNC_IPF_DEV_TYPE_TO_ROLE else None,
                location_name=device_record.location.name,
                vendor=str(device_record.device_type.manufacturer),
                status=device_record.status.name,
                serial_number=device_record.serial if device_record.serial else "",
            )
            if device_record.platform:
                device.platform = device_record.platform.name
            if device_record.virtual_chassis:
                device.vc_name = device_record.virtual_chassis.name
                device.vc_position = device_record.vc_position
                device.vc_priority = device_record.vc_priority
                device.vc_master = bool(device_record.virtual_chassis.master == device_record)
            try:
                self.add(device)
            except ObjectAlreadyExists:
                logger.warning(f"Duplicate device discovered, {device_record.name}")
                continue

            location.add_child(device)
            self.load_interfaces(device_record=device_record, diffsync_device=device)

    def load_vlans(self, filtered_vlans: List, location, location_record):
        """Add Nautobot VLAN objects as DiffSync VLAN models."""
        for vlan_record in filtered_vlans:
            vlan = self.vlan(
                name=vlan_record.name,
                location=location_record.name,
                status=vlan_record.status.name,
                vid=vlan_record.vid,
                vlan_pk=vlan_record.pk,
                description=vlan_record.description,
            )
            try:
                self.add(vlan)
            except ObjectAlreadyExists:
                logger.warning(f"Duplicate VLAN discovered, {vlan_record.name}")
                continue
            location.add_child(vlan)

    def get_initial_location(self, ssot_tag: Tag):
        """Identify the location objects based on user defined job inputs.

        Args:
            ssot_tag (Tag): Tag used for filtering
        """
        # Simple check / validate Tag is present.
        if self.sync_ipfabric_tagged_only:
            location_objects = Location.objects.filter(tags__name=ssot_tag.name)
            if self.location_filter:
                location_objects = location_objects.filter(name=self.location_filter.name)
                if not location_objects:
                    logger.warning(
                        f"{self.location_filter.name} was used to filter, alongside SSoT Tag. {self.location_filter.name} is not tagged."
                    )
        elif not self.sync_ipfabric_tagged_only:
            if self.location_filter:
                location_objects = Location.objects.filter(name=self.location_filter.name)
            else:
                location_objects = Location.objects.all()
        return location_objects.select_related("status")

    @transaction.atomic
    def load_data(self):
        """Add Nautobot Location objects as DiffSync Location models."""
        location_objects = self.get_initial_location(self.ssot_tag)
        # The parent object that stores all children, is the Location.
        if self.job.debug:
            logger.debug("Found %s Nautobot Location objects to start sync from", len(location_objects))

        if location_objects:
            for location_record in location_objects:
                try:
                    location = self.location(
                        name=location_record.name,
                        site_id=location_record.custom_field_data.get("ipfabric_site_id"),
                        status=location_record.status.name,
                    )
                except AttributeError:
                    logger.error(
                        "Error loading %s, invalid or missing attributes on object. Skipping...", location_record
                    )
                    continue
                self.add(location)
                try:
                    # Load Location's Children - Devices with Interfaces, if any.
                    if self.sync_ipfabric_tagged_only:
                        nautobot_location_devices = Device.objects.filter(
                            Q(location=location_record) & Q(tags=self.ssot_tag)
                        )
                    else:
                        nautobot_location_devices = Device.objects.filter(location=location_record)
                    self.load_device(nautobot_location_devices, location)

                    # Load Location Children - Vlans, if any.
                    nautobot_location_vlans = (
                        VLAN.objects.filter(location=location_record)
                        .select_related("status")
                        .prefetch_related("locations")
                    )
                    self.load_vlans(nautobot_location_vlans, location, location_record)
                except Location.DoesNotExist:
                    logger.error("Unable to find Location, %s.", location_record)
        else:
            logger.warning("No Nautobot records to load.")

    def load(self):
        """Load data from Nautobot."""
        self.load_data()
