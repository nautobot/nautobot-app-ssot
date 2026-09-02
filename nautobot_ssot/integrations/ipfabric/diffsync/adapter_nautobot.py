# pylint: disable=duplicate-code
# pylint: disable=too-many-arguments
# Load method is packed with conditionals  #  pylint: disable=too-many-branches
# The adapter carries the job's options  #  pylint: disable=too-many-instance-attributes
"""DiffSync adapter class for Nautobot as source-of-truth."""

import logging
from collections import defaultdict
from typing import Any, ClassVar, Dict, List, Optional

from diffsync import Adapter
from diffsync.exceptions import ObjectAlreadyExists, ObjectNotFound
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import Device, Location
from nautobot.extras.models import Tag
from nautobot.ipam.models import VLAN, Interface
from netutils.ip import cidr_to_netmask
from netutils.mac import mac_to_format

import nautobot_ssot.integrations.ipfabric.utilities.cables as tonb_cables
import nautobot_ssot.integrations.ipfabric.utilities.nbutils as tonb_utils
from nautobot_ssot.integrations.ipfabric.bulk_writes import PendingWrites
from nautobot_ssot.integrations.ipfabric.constants import (
    DEFAULT_INTERFACE_MAC,
    DEFAULT_INTERFACE_MTU,
    PSEUDO_MANAGEMENT_INTERFACE_NAME,
    SYNC_IPF_DEV_TYPE_TO_ROLE,
)
from nautobot_ssot.integrations.ipfabric.diffsync import DiffSyncModelAdapters
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache

logger = logging.getLogger("nautobot.ssot.ipfabric")


# How many objects to delete per statement. Django walks the relations of a whole batch once, so
# larger batches cost fewer queries, at the price of a longer `IN` list and a wider lock.
DELETE_BATCH_SIZE = 1000

# How many rows bulk mode will hold before writing them. Without a ceiling a sync of a hundred
# thousand Interfaces would keep every one of them, and their addresses, in memory until the end.
PENDING_WRITE_HIGH_WATER = 5000


def delete_objects(nautobot_objects: List):
    """Delete the given Nautobot objects, in as few statements as their relations allow.

    Deleting one at a time makes Django walk that object's relations and issue its own statements;
    deleting a batch walks them once. A batch Nautobot refuses is retried an object at a time, so one
    protected object neither takes the rest with it nor goes unreported.
    """
    by_model = defaultdict(list)
    for nautobot_object in nautobot_objects:
        by_model[type(nautobot_object)].append(nautobot_object)

    for model, objects in by_model.items():
        for start in range(0, len(objects), DELETE_BATCH_SIZE):
            batch = objects[start : start + DELETE_BATCH_SIZE]
            try:
                # Its own savepoint, so a refused batch leaves the transaction usable. Deferring the
                # change log within it turns one entry per deleted object into one bulk insert.
                with transaction.atomic(), tonb_utils.deferred_change_logging():
                    model.objects.filter(pk__in=[nautobot_object.pk for nautobot_object in batch]).delete()
            except IntegrityError:
                delete_objects_one_at_a_time(batch)


def delete_objects_one_at_a_time(nautobot_objects: List):
    """Delete the given Nautobot objects individually, naming each one Nautobot refuses."""
    for nautobot_object in nautobot_objects:
        try:
            with transaction.atomic():
                nautobot_object.delete()
        except ProtectedError:
            logger.warning("Deletion failed protected object", extra={"object": nautobot_object})
        except IntegrityError:
            logger.warning(f"Deletion failed due to IntegrityError with {nautobot_object}")


class NautobotDiffSync(DiffSyncModelAdapters):
    """Nautobot adapter for DiffSync."""

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
        bulk_write_mode: bool = False,
        **kwargs,
    ):
        """Initialize the NautobotDiffSync."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.sync_ipfabric_tagged_only = sync_ipfabric_tagged_only
        self.location_filter = location_filter
        # Present only in bulk write mode, so that whether writes are batched is one fact rather
        # than two. Passed in rather than set on the class, so two runs in one worker cannot see
        # each other's choice; `safe_delete_mode` is still set on the class, so two runs share it.
        self.pending = PendingWrites() if bulk_write_mode else None
        # Per adapter rather than per class, so that a run which fails before `sync_complete` cannot
        # leave objects queued for a later run in the same worker to delete.
        self.objects_to_delete = defaultdict(list)
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
        try:
            # Deletion reads objects back from the database, so anything bulk mode has queued has to
            # be written before it runs.
            self.flush_pending_writes()

            for grouping in (
                "_vlan",
                "_interface",
                "_device",
                "_location",
            ):
                if not self.safe_delete_mode:
                    delete_objects(self.objects_to_delete[grouping])
                self.objects_to_delete[grouping] = []
        finally:
            # Thread local, so on a long lived worker these hold what this run cached until something
            # empties them. Emptied even when the writes above fail, so that a failure cannot hand a
            # later run objects whose rows were rolled back.
            job_scoped_cache.clear_all()
        return super().sync_complete(source, *args, **kwargs)

    def flush_pending_writes_if_full(self) -> int:
        """Write the queue if it has grown past what is worth holding in memory.

        Called once a model has finished its own work, which is the only safe point: a queue flushed
        part way through an operation would miss whatever that operation went on to set, such as a
        Device's virtual chassis fields.
        """
        if len(self.pending) < PENDING_WRITE_HIGH_WATER:
            return 0
        return self.flush_pending_writes()

    def flush_pending_writes(self) -> int:
        """Write whatever bulk mode has queued, and report what was written.

        Called before anything that reads those objects back from the database, and at the end of
        the sync. A no-op when nothing is queued, so callers need not check the mode first.
        """
        if not self.pending:
            return 0
        counts = self.pending.counts()
        written = self.pending.flush()
        # Rows exist now that did not when these lookups last ran, and one of them caching that a
        # Device could not be found is enough to lose every Cable terminating on it.
        job_scoped_cache.clear_group(tonb_utils.BULK_WRITTEN_LOOKUPS)
        self.job.logger.info("Wrote %d queued rows in bulk mode: %s", written, counts)
        return written

    def load_interfaces(self, device_record: Device, diffsync_device):
        """Import a single Nautobot Interface object as a DiffSync Interface model."""
        device_primary_ip = None
        if self.scope.ip_addresses:
            device_primary_ip = device_record.primary_ip4 or device_record.primary_ip6

        for interface_record in device_record.interfaces.all():
            if not self.scope.ip_addresses and interface_record.name == PSEUDO_MANAGEMENT_INTERFACE_NAME:
                # The IP Fabric adapter only fabricates this Interface to carry a NAT management
                # address, so out of scope it reports none. Skipped here to match: reporting one an
                # earlier run created would leave it looking absent from the source, and deleted.
                continue
            # Avoid .first() to preserve prefetch cache
            ip_addresses = interface_record.ip_addresses.all() if self.scope.ip_addresses else []
            has_a_subnet = (device_record.name, interface_record.name) not in self.interfaces_without_a_subnet
            if ip_addresses and has_a_subnet:
                ip_address_obj = ip_addresses[0]
                ip_address = ip_address_obj.host
                subnet_mask = cidr_to_netmask(ip_address_obj.mask_length)
            else:
                # An Interface IP Fabric reports no subnet for reports no address on either side, so
                # that the mask Nautobot holds is left alone rather than diffed against one the
                # source does not have. See `interfaces_without_a_subnet`.
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
                ip_is_primary=(
                    self.scope.primary_ip and device_primary_ip is not None and ip_address_obj == device_primary_ip
                ),
                ip_address=ip_address,
            )
            self.add(interface)
            diffsync_device.add_child(interface)

    def load_cables(self, device_queryset):
        """Add Nautobot Cable objects as DiffSync Cable models.

        Only links whose Interfaces were both loaded are added, matching the endpoints IP Fabric can
        report. A Cable with one end out of scope would otherwise look absent from IP Fabric and be
        deleted on every run.
        """
        endpoints_by_cable = defaultdict(list)
        for interface_record in tonb_cables.cabled_interfaces(device_queryset):
            endpoint = (interface_record.device.name, interface_record.name)
            try:
                self.get(self.interface, {"name": endpoint[1], "device_name": endpoint[0]})
            except ObjectNotFound:
                # The Interface's Device was skipped while loading, so the link is out of scope.
                continue
            endpoints_by_cable[interface_record.cable].append(endpoint)

        for cable_record, endpoints in endpoints_by_cable.items():
            if len(endpoints) == 1:
                if self.job.debug:
                    logger.debug("Not loading Cable %s as only one of its ends is in scope", cable_record.pk)
                continue
            if len(endpoints) > 2:
                logger.warning(
                    f"Not loading Cable {cable_record.pk} as it terminates on {len(endpoints)} in scope Interfaces, "
                    "which IP Fabric's point to point connectivity matrix cannot describe"
                )
                continue
            endpoint_a, endpoint_b = tonb_cables.canonical_endpoints(*endpoints)
            cable = self.cable(
                termination_a_device=endpoint_a[0],
                termination_a_name=endpoint_a[1],
                termination_b_device=endpoint_b[0],
                termination_b_name=endpoint_b[1],
                status=cable_record.status.name,
                cable_pk=cable_record.pk,
            )
            try:
                self.add(cable)
            except ObjectAlreadyExists:
                logger.warning(f"Duplicate Cable discovered, {cable.get_unique_id()}")

    def get_in_scope_devices(self, location_objects):
        """Return the Devices at the given Locations that this sync covers.

        Shared by Device loading and Cable loading, so that Cables cannot load for Devices whose
        Interfaces did not.
        """
        devices = Device.objects.filter(location__in=location_objects)
        if self.sync_ipfabric_tagged_only:
            devices = devices.filter(tags=self.ssot_tag)
        return devices

    def load_devices(self, filtered_devices: List, locations_by_name: Dict[str, Any]):
        """Load Devices from Nautobot, placing each under the Location it belongs to.

        Every Location's Devices come from one query, streamed in chunks. Querying per Location
        instead would repeat the Interface and IP Address prefetches once per Location, which for
        an estate of many Locations is where the load spends most of its queries.
        """
        related = [
            "location",
            "device_type__manufacturer",
            "role",
            "status",
            "platform",
            "virtual_chassis",
            "virtual_chassis__master",
        ]
        # Only fetch the relations something in scope reads: the primary IP decides whether an
        # Interface holds it, and the Interfaces themselves are only walked when they are in scope.
        prefetch = None
        if self.scope.ip_addresses:
            related += ["primary_ip4", "primary_ip6"]
            prefetch = "interfaces__ip_addresses"
        elif self.scope.interfaces:
            prefetch = "interfaces"
        devices = filtered_devices.select_related(*related)
        if prefetch:
            devices = devices.prefetch_related(prefetch)
        optimized_query = devices.iterator(1000)
        for device_record in optimized_query:
            location = locations_by_name.get(device_record.location.name)
            if location is None:
                # Its Location failed to load, so there is no parent to add the Device to.
                logger.error("Unable to find Location, %s.", device_record.location.name)
                continue
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
            if self.scope.interfaces:
                self.load_interfaces(device_record=device_record, diffsync_device=device)

    def load_vlans(self, location_objects, locations_by_name: Dict[str, Any]):
        """Add Nautobot VLAN objects as DiffSync VLAN models.

        One query covers every Location. A VLAN assigned to several of them is loaded once per
        Location, as each is a separate DiffSync VLAN, matching how IP Fabric reports VLANs per site.
        """
        filtered_vlans = (
            VLAN.objects.filter(locations__in=location_objects)
            .select_related("status")
            .prefetch_related("locations")
            .distinct()
        )
        for vlan_record in filtered_vlans:
            for location_record in vlan_record.locations.all():
                location = locations_by_name.get(location_record.name)
                if location is None:
                    # A Location the VLAN is also assigned to, but which this sync does not cover.
                    continue
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

        if not location_objects:
            logger.warning("No Nautobot records to load.")
            return

        locations_by_name = {}
        for location_record in location_objects:
            try:
                location = self.location_model(
                    location_record.name,
                    site_id=location_record.custom_field_data.get("ipfabric_site_id"),
                    status=location_record.status.name,
                )
            except AttributeError:
                logger.error("Error loading %s, invalid or missing attributes on object. Skipping...", location_record)
                continue
            self.add(location)
            locations_by_name[location_record.name] = location

        # Children are loaded once for every Location rather than once per Location, so that the
        # number of queries a load takes does not grow with the number of Locations in scope.
        self.load_devices(self.get_in_scope_devices(location_objects), locations_by_name)
        if self.scope.vlans:
            self.load_vlans(location_objects, locations_by_name)

        # Loaded after every Location, as a link may terminate on Devices in two of them.
        if self.scope.cables:
            self.load_cables(self.get_in_scope_devices(location_objects))

    def load(self):
        """Load data from Nautobot."""
        self.load_data()
