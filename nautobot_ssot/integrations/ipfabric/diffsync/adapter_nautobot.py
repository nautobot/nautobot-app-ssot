#  pylint: disable=too-many-arguments
# Load method is packed with conditionals  #  pylint: disable=too-many-branches
"""DiffSync adapter class for Nautobot as source-of-truth."""
from collections import defaultdict
from typing import Any, ClassVar, List

from diffsync import DiffSync
from diffsync.exceptions import ObjectAlreadyExists
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError, Q
from nautobot.dcim.models import Device, Site
from nautobot.extras.models import Tag
from nautobot.ipam.models import VLAN, Interface
from nautobot.utilities.choices import ColorChoices
from netutils.mac import mac_to_format

from nautobot_ssot_ipfabric.diffsync import DiffSyncModelAdapters

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot_ipfabric", {})
DEFAULT_INTERFACE_TYPE = CONFIG.get("default_interface_type", "1000base-t")
DEFAULT_INTERFACE_MTU = CONFIG.get("default_interface_mtu", 1500)
DEFAULT_INTERFACE_MAC = CONFIG.get("default_interface_mac", "00:00:00:00:00:01")
DEFAULT_DEVICE_ROLE = CONFIG.get("default_device_role", "Network Device")


class NautobotDiffSync(DiffSyncModelAdapters):
    """Nautobot adapter for DiffSync."""

    objects_to_delete = defaultdict(list)

    _vlan: ClassVar[Any] = VLAN
    _device: ClassVar[Any] = Device
    _site: ClassVar[Any] = Site
    _interface: ClassVar[Any] = Interface

    def __init__(
        self,
        job,
        sync,
        sync_ipfabric_tagged_only: bool,
        site_filter: Site,
        *args,
        **kwargs,
    ):
        """Initialize the NautobotDiffSync."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.sync_ipfabric_tagged_only = sync_ipfabric_tagged_only
        self.site_filter = site_filter

    def sync_complete(self, source: DiffSync, *args, **kwargs):
        """Clean up function for DiffSync sync.

        Once the sync is complete, this function runs deleting any objects
        from Nautobot that need to be deleted in a specific order.

        Args:
            source (DiffSync): DiffSync
        """
        for grouping in (
            "_vlan",
            "_interface",
            "_device",
            "_site",
        ):
            for nautobot_object in self.objects_to_delete[grouping]:
                if NautobotDiffSync.safe_delete_mode:
                    continue
                try:
                    nautobot_object.delete()
                except ProtectedError:
                    self.job.log_failure(obj=nautobot_object, message="Deletion failed protected object")
                except IntegrityError:
                    self.job.log_failure(
                        obj=nautobot_object, message=f"Deletion failed due to IntegrityError with {nautobot_object}"
                    )

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
            interface = self.interface(
                diffsync=self,
                status=device_record.status.name,
                name=interface_record.name,
                device_name=device_record.name,
                description=interface_record.description if interface_record.description else "",
                enabled=True,
                mac_address=mac_to_format(str(interface_record.mac_address), "MAC_COLON_TWO").upper()
                if interface_record.mac_address
                else DEFAULT_INTERFACE_MAC,
                subnet_mask="255.255.255.255",
                mtu=interface_record.mtu if interface_record.mtu else DEFAULT_INTERFACE_MTU,
                type=DEFAULT_INTERFACE_TYPE,
                mgmt_only=interface_record.mgmt_only if interface_record.mgmt_only else False,
                pk=interface_record.pk,
                ip_is_primary=interface_record.ip_addresses.first() == device_primary_ip
                if device_primary_ip
                else False,
                ip_address=str(interface_record.ip_addresses.first().host)
                if interface_record.ip_addresses.first()
                else None,
            )
            self.add(interface)
            diffsync_device.add_child(interface)

    def load_device(self, filtered_devices: List, location):
        """Load Devices from Nautobot."""
        for device_record in filtered_devices:
            self.job.log_debug(message=f"Loading Nautobot Device: {device_record.name}")
            device = self.device(
                diffsync=self,
                name=device_record.name,
                model=str(device_record.device_type),
                role=str(device_record.device_role) if str(device_record.device_role) else DEFAULT_DEVICE_ROLE,
                location_name=device_record.site.name,
                vendor=str(device_record.device_type.manufacturer),
                status=device_record.status.name,
                serial_number=device_record.serial if device_record.serial else "",
            )
            try:
                self.add(device)
            except ObjectAlreadyExists:
                self.job.log_debug(message=f"Duplicate device discovered, {device_record.name}")
                continue

            location.add_child(device)
            self.load_interfaces(device_record=device_record, diffsync_device=device)

    def load_vlans(self, filtered_vlans: List, location):
        """Add Nautobot VLAN objects as DiffSync VLAN models."""
        for vlan_record in filtered_vlans:
            if not vlan_record:
                continue
            vlan = self.vlan(
                diffsync=self,
                name=vlan_record.name,
                site=vlan_record.site.name,
                status=vlan_record.status.name if vlan_record.status else "Active",
                vid=vlan_record.vid,
                vlan_pk=vlan_record.pk,
                description=vlan_record.description,
            )
            try:
                self.add(vlan)
            except ObjectAlreadyExists:
                self.job.log_debug(message=f"Duplicate VLAN discovered, {vlan_record.name}")
                continue
            location.add_child(vlan)

    def get_initial_site(self, ssot_tag: Tag):
        """Identify the site objects based on user defined job inputs.

        Args:
            ssot_tag (Tag): Tag used for filtering
        """
        # Simple check / validate Tag is present.
        if self.sync_ipfabric_tagged_only:
            site_objects = Site.objects.filter(tags__slug=ssot_tag.slug)
            if self.site_filter:
                site_objects = Site.objects.filter(Q(name=self.site_filter.name) & Q(tags__slug=ssot_tag.slug))
                if not site_objects:
                    self.job.log_warning(
                        message=f"{self.site_filter.name} was used to filter, alongside SSoT Tag. {self.site_filter.name} is not tagged."
                    )
        elif not self.sync_ipfabric_tagged_only:
            if self.site_filter:
                site_objects = Site.objects.filter(name=self.site_filter.name)
            else:
                site_objects = Site.objects.all()
        return site_objects

    @transaction.atomic
    def load_data(self):
        """Add Nautobot Site objects as DiffSync Location models."""
        ssot_tag, _ = Tag.objects.get_or_create(
            slug="ssot-synced-from-ipfabric",
            name="SSoT Synced from IPFabric",
            defaults={
                "description": "Object synced at some point from IPFabric to Nautobot",
                "color": ColorChoices.COLOR_LIGHT_GREEN,
            },
        )
        site_objects = self.get_initial_site(ssot_tag)
        # The parent object that stores all children, is the Site.
        self.job.log_debug(message=f"Found {site_objects.count()} Nautobot Site objects to start sync from")

        if site_objects:
            for site_record in site_objects:
                try:
                    location = self.location(
                        diffsync=self,
                        name=site_record.name,
                        site_id=site_record.custom_field_data.get("ipfabric-site-id"),
                        status=site_record.status.name,
                    )
                except AttributeError:
                    self.job.log_debug(
                        message=f"Error loading {site_record}, invalid or missing attributes on object. Skipping..."
                    )
                    continue
                self.add(location)
                try:
                    # Load Site's Children - Devices with Interfaces, if any.
                    if self.sync_ipfabric_tagged_only:
                        nautobot_site_devices = Device.objects.filter(Q(site=site_record) & Q(tags__slug=ssot_tag.slug))
                    else:
                        nautobot_site_devices = Device.objects.filter(site=site_record)
                    if nautobot_site_devices.exists():
                        self.load_device(nautobot_site_devices, location)

                    # Load Site Children - Vlans, if any.
                    nautobot_site_vlans = VLAN.objects.filter(site=site_record)
                    if not nautobot_site_vlans.exists():
                        continue
                    self.load_vlans(nautobot_site_vlans, location)
                except Site.DoesNotExist:
                    self.job.log_info(message=f"Unable to find Site, {site_record}.")
        else:
            self.job.log_warning(message="No Nautobot records to load.")

    def load(self):
        """Load data from Nautobot."""
        self.load_data()
