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
from nautobot.ipam.models import VLAN, VRF, Interface, RouteTarget, VRFDeviceAssignment
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

# The order `sync_complete` deletes the groupings in, children before whatever they hang off: a
# Cable terminates on an Interface and an IP Address sits on one, so both go before the Interface,
# and an Interface before its Device. `safe_delete` derives the grouping from the object's class
# name, so a model added later lands in a grouping nothing here names; those are drained last and
# reported, rather than accumulating unread as `_ipaddress` and `_cable` did.
#
# VRFs come after the Interfaces and Devices that may point at one, and Route Targets after the VRFs
# that name them. Assignments come before both ends they join, which Nautobot would otherwise cascade
# away underneath them.
DELETE_ORDER = (
    "_cable",
    "_ipaddress",
    "_vlan",
    "_interface",
    "_vrfdeviceassignment",
    "_device",
    "_location",
    "_vrf",
    "_routetarget",
)

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
        # Placeholder Interfaces found while strict about Interfaces, reported once loading is done.
        self.placeholder_interfaces = []
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

            unordered = sorted(set(self.objects_to_delete) - set(DELETE_ORDER))
            if unordered:
                self.job.logger.warning(
                    "Deleting %s after everything else, as no order is declared for them. Add them to "
                    "`DELETE_ORDER` so they are removed before whatever they hang off.",
                    ", ".join(unordered),
                )
            for grouping in (*DELETE_ORDER, *unordered):
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
        for interface_record in device_record.interfaces.all():
            if interface_record.name == PSEUDO_MANAGEMENT_INTERFACE_NAME and (
                not self.carries_pseudo_management_interface()
            ):
                # The IP Fabric adapter only fabricates this Interface to carry a NAT management
                # address, and reports none either with addresses out of scope or while strict about
                # Interfaces. Skipped here to match: reporting one an earlier run created would leave
                # it looking absent from the source, and deleted. Counted so that the ones already in
                # Nautobot can be found, since strictness stops new ones rather than removing old.
                if self.strict.interfaces:
                    self.placeholder_interfaces.append(f"{device_record.name}:{interface_record.name}")
                continue
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
                mtu=interface_record.mtu if interface_record.mtu else DEFAULT_INTERFACE_MTU,
                type=interface_record.type,
                mgmt_only=interface_record.mgmt_only if interface_record.mgmt_only else False,
                pk=interface_record.pk,
            )
            self.add(interface)
            diffsync_device.add_child(interface)
            self.load_interface_addresses(device_record, interface_record, interface)

    def load_interface_addresses(self, device_record: Device, interface_record, interface):
        """Add each address on the Interface as a DiffSync model of its own.

        An address IP Fabric reports no usable subnet for is withheld here as well as there, so that
        the mask Nautobot holds is left alone rather than diffed against one the source does not
        have. Withheld per address rather than per Interface: an Interface carrying a second address
        that is fine must still report that one. See `addresses_without_a_subnet`.
        """
        if not self.scope.ip_addresses:
            return
        # Both, not whichever comes first: a dual stack Device carries a primary of each version,
        # and comparing against one of them would report the other's address as never primary while
        # the source says it is, which is a difference no sync could ever apply away. Both are
        # `select_related` while addresses are in scope, so neither costs a query here.
        device_primary_ips = {addr for addr in (device_record.primary_ip4, device_record.primary_ip6) if addr}
        for address_record in interface_record.ip_addresses.all():
            if (device_record.name, interface_record.name, address_record.host) in self.addresses_without_a_subnet:
                continue
            address = self.interface_address(
                device_name=device_record.name,
                interface_name=interface_record.name,
                host=address_record.host,
                mask_length=address_record.mask_length,
                is_primary=self.scope.primary_ip and address_record in device_primary_ips,
                status=address_record.status.name,
            )
            self.add(address)
            interface.add_child(address)

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
            # `__status` because each address reports its own; without it the walk below costs a
            # query per address, which is a hundred thousand of them on a real estate.
            prefetch = "interfaces__ip_addresses__status"
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
                    # Nautobot does not constrain a VLAN ID to be unique at a Location, so two can
                    # carry the same one.
                    logger.warning(
                        f"Duplicate VLAN discovered at {location_record.name}: VLAN ID "
                        f"{vlan_record.vid}, named {vlan_record.name}"
                    )
                    continue
                location.add_child(vlan)

    def load_interface_vrfs(self, filtered_devices):
        """Add the VRF each Nautobot Interface is in as DiffSync InterfaceVrf models.

        Only Interfaces that are in one are loaded, matching what IP Fabric's VRF interfaces table
        reports, and only those whose VRF this run loaded.
        """
        interfaces = Interface.objects.filter(
            device__in=filtered_devices,
            vrf__isnull=False,
            vrf__namespace=tonb_utils.get_global_namespace(),
        ).values_list("device__name", "name", "vrf__name")
        for device_name, interface_name, vrf_name in interfaces:
            try:
                self.get(self.vrf, vrf_name)
            except ObjectNotFound:
                # Its VRF was not loaded, so this run holds no opinion about the Interface either.
                continue
            self.add(
                self.interface_vrf(
                    adapter=self,
                    device_name=device_name,
                    interface_name=interface_name,
                    vrf_name=vrf_name,
                )
            )

    def load_vrf_device_assignments(self, filtered_devices):
        """Add Nautobot's VRF to Device assignments as DiffSync models.

        Scoped to the Devices this run covers and to the VRFs it loaded, so that an assignment the
        source cannot describe is not reported as absent from it. That is also why no flag is needed
        for a Location filtered run, unlike the VRFs themselves: an assignment belongs to a Device,
        and Devices are already narrowed by the filter, so both sides narrow together.
        """
        assignments = VRFDeviceAssignment.objects.filter(
            vrf__namespace=tonb_utils.get_global_namespace(),
            device__in=filtered_devices,
        ).values_list("vrf__name", "device__name")
        for vrf_name, device_name in assignments:
            try:
                self.get(self.vrf, vrf_name)
            except ObjectNotFound:
                # Its VRF was not loaded, so this run holds no opinion about the assignment either.
                continue
            self.add(self.vrf_device_assignment(adapter=self, vrf_name=vrf_name, device_name=device_name))

    def load_route_targets(self):
        """Add the Route Targets this integration created as DiffSync RouteTarget models.

        Scoped to the ones carrying the sync's Tag, rather than every Route Target Nautobot holds.
        A Route Target has no Location, no Device and no Namespace — it is a bare value, unique
        across the whole of Nautobot — so there is no containment to bound a load by, and loading
        all of them would have this sync delete every Route Target another system owns the moment
        IP Fabric stopped reporting it.

        A Route Target IP Fabric reports that is absent here is still adopted rather than duplicated,
        since the name is unique: it is reported as a create, and creating it marks the one Nautobot
        already holds. That is what lets a first run converge against an existing estate.
        """
        for route_target in RouteTarget.objects.filter(tags=self.ssot_tag).values_list("name", flat=True):
            self.add(self.network_wide(self.route_target, name=route_target))

    def load_vrfs(self):
        """Add Nautobot VRFs in the Global Namespace as DiffSync Vrf models.

        A name the Namespace holds twice is loaded as neither of them. Nautobot constrains a VRF to
        a unique route distinguisher within its Namespace but not to a unique name, while IP Fabric
        reports a VRF name as network wide, so there is nothing to say which of the two its report
        describes. Loading one would have the sync write IP Fabric's values over whichever came
        first; loading neither leaves both alone and reports why.
        """
        vrfs = VRF.objects.filter(namespace=tonb_utils.get_global_namespace()).select_related("status")
        if self.scope.route_targets:
            vrfs = vrfs.prefetch_related("import_targets", "export_targets")
        by_name = defaultdict(list)
        for vrf_record in vrfs:
            by_name[vrf_record.name].append(vrf_record)

        for name, vrf_records in by_name.items():
            if len(vrf_records) > 1:
                self.ambiguous_vrf_names.add(name)
                logger.warning(
                    "Not syncing the VRF named %s, as the Global Namespace holds %d VRFs of that name "
                    "and IP Fabric reports nothing that tells them apart",
                    name,
                    len(vrf_records),
                )
                continue
            vrf_record = vrf_records[0]
            # Reported as none when route targets are out of scope, which is what the IP Fabric
            # adapter reports as well, so the two match and neither list is written.
            import_targets, export_targets = [], []
            if self.scope.route_targets:
                import_targets = sorted(target.name for target in vrf_record.import_targets.all())
                export_targets = sorted(target.name for target in vrf_record.export_targets.all())
            self.add(
                self.network_wide(
                    self.vrf,
                    name=name,
                    rd=vrf_record.rd or None,
                    status=vrf_record.status.name if vrf_record.status else "Active",
                    import_targets=import_targets,
                    export_targets=export_targets,
                    conflict=vrf_record.custom_field_data.get(tonb_utils.VRF_CONFLICT_CF_NAME) or "",
                )
            )

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
        # Not a child of any Location, so loaded before the tree below and regardless of whether
        # that tree has a root: an estate with no Locations still has VRFs to report.
        if self.scope.route_targets:
            self.load_route_targets()
        if self.scope.vrfs:
            self.load_vrfs()

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

        # Loaded last, as it needs the Devices above and the VRFs loaded before them.
        if self.scope.device_vrfs:
            self.load_vrf_device_assignments(self.get_in_scope_devices(location_objects))
        if self.scope.interface_vrfs:
            self.load_interface_vrfs(self.get_in_scope_devices(location_objects))

        if self.placeholder_interfaces:
            self.job.logger.warning(
                "Leaving %d placeholder Interfaces in place, as being strict about Interfaces stops "
                "new ones rather than removing those an earlier run created: %s",
                len(self.placeholder_interfaces),
                ", ".join(sorted(self.placeholder_interfaces)),
            )

    def load(self):
        """Load data from Nautobot."""
        self.load_data()
