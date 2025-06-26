"""Nautobot Adapter for Meraki SSoT plugin."""

from collections import defaultdict
from typing import Optional

from diffsync import Adapter
from diffsync.enum import DiffSyncModelFlags
from diffsync.exceptions import ObjectNotFound
from django.contrib.contenttypes.models import ContentType
from django.db.models import ProtectedError
from nautobot.dcim.models import (
    Device,
    DeviceType,
    Interface,
    Location,
    LocationType,
    Manufacturer,
    Platform,
    SoftwareVersion,
)
from nautobot.extras.models import Note, Role, Status
from nautobot.ipam.models import IPAddress, IPAddressToInterface, Namespace, Prefix, PrefixLocationAssignment
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.meraki.diffsync.models.nautobot import (
    NautobotDevice,
    NautobotHardware,
    NautobotIPAddress,
    NautobotIPAssignment,
    NautobotNetwork,
    NautobotOSVersion,
    NautobotPort,
    NautobotPrefix,
    NautobotPrefixLocation,
)
from nautobot_ssot.integrations.meraki.utils.nautobot import get_tag_strings


class NautobotAdapter(Adapter):  # pylint: disable=too-many-instance-attributes
    """DiffSync adapter for Nautobot."""

    network = NautobotNetwork
    hardware = NautobotHardware
    osversion = NautobotOSVersion
    device = NautobotDevice
    port = NautobotPort
    prefix = NautobotPrefix
    prefixlocation = NautobotPrefixLocation
    ipaddress = NautobotIPAddress
    ipassignment = NautobotIPAssignment

    top_level = ["network", "hardware", "osversion", "device", "prefix", "prefixlocation", "ipaddress", "ipassignment"]

    def __init__(self, job, sync=None, tenant: Optional[Tenant] = None):
        """Initialize Nautobot.

        Args:
            job (object): Nautobot job.
            sync (object, optional): Nautobot DiffSync. Defaults to None.
            tenant (Tenant, optional): Nautobot Tenant to assign to loaded objects. Defaults to None.
        """
        super().__init__()
        self.job = job
        self.sync = sync
        self.tenant = tenant
        self.objects_to_create = defaultdict(list)
        self.objects_to_delete = defaultdict(list)
        self.status_map = {}
        self.tenant_map = {}
        self.locationtype_map = {}
        self.region_map = {}
        self.site_map = {}
        self.platform_map = {}
        self.manufacturer_map = {}
        self.devicerole_map = {}
        self.devicetype_map = {}
        self.device_map = {}
        self.port_map = {}
        self.namespace_map = {}
        self.prefix_map = {}
        self.ipaddr_map = {}
        self.contenttype_map = {}
        self.version_map = {}

    def load_sites(self):
        """Load Site data from Nautobot into DiffSync model."""
        for site in Location.objects.filter(location_type=self.job.network_loctype):
            self.site_map[site.name] = site
            new_site, _ = self.get_or_instantiate(
                self.network,
                ids={"name": site.name, "parent": site.parent.name if site.parent else None},
                attrs={
                    "notes": "",
                    "tags": get_tag_strings(list_tags=site.tags),
                    "timezone": str(site.time_zone) if site.time_zone else None,
                    "tenant": site.tenant.name if site.tenant else None,
                    "uuid": site.id,
                },
            )
            if site.notes:
                note = site.notes.last()
                new_site.notes = note.note.rstrip()

    def load_devicetypes(self):
        """Load DeviceType data from Nautobot into DiffSync model."""
        for devtype in DeviceType.objects.filter(manufacturer__name="Cisco Meraki"):
            try:
                self.get(self.hardware, devtype.model)
            except ObjectNotFound:
                new_dt = self.hardware(model=devtype.model, uuid=devtype.id)
                if self.tenant:
                    new_dt.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
                self.add(new_dt)
                self.devicetype_map[devtype.model] = devtype.id

    def load_softwareversions(self):
        """Load SoftwareVersion data from Nautobot into DiffSync model."""
        for ver in SoftwareVersion.objects.filter(platform__name="Cisco Meraki"):
            self.get_or_instantiate(self.osversion, ids={"version": ver.version}, attrs={"uuid": ver.id})
            self.version_map[ver.version] = ver.id

    def load_devices(self):
        """Load Device data from Nautobot into DiffSync model."""
        if self.tenant:
            devices = Device.objects.filter(tenant=self.tenant)
        else:
            devices = Device.objects.filter(_custom_field_data__system_of_record="Meraki SSoT")
        for dev in devices:
            try:
                self.get(self.device, dev.name)
            except ObjectNotFound:
                self.device_map[dev.name] = dev.id
                self.port_map[dev.name] = {}
                new_dev = self.device(
                    name=dev.name,
                    controller_group=dev.controller_managed_device_group.name
                    if dev.controller_managed_device_group
                    else None,
                    serial=dev.serial,
                    status=dev.status.name,
                    role=dev.role.name,
                    model=dev.device_type.model,
                    notes="",
                    network=dev.location.name,
                    tenant=dev.tenant.name if dev.tenant else None,
                    uuid=dev.id,
                    version=dev.software_version.version if dev.software_version else None,
                )
                if dev.notes:
                    note = dev.notes.last()
                    new_dev.notes = note.note.rstrip()
                if self.tenant:
                    new_dev.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
                self.add(new_dev)

    def load_ports(self):
        """Load Port data from Nautobot into DiffSync model."""
        if self.tenant:
            ports = Interface.objects.filter(device__tenant=self.tenant)
        else:
            ports = Interface.objects.filter(_custom_field_data__system_of_record="Meraki SSoT")
        for intf in ports:
            try:
                self.get(self.port, {"name": intf.name, "device": intf.device.name})
            except ObjectNotFound:
                self.port_map[intf.device.name][intf.name] = intf.id
                new_port = self.port(
                    name=intf.name,
                    device=intf.device.name,
                    management=intf.mgmt_only,
                    enabled=intf.enabled,
                    port_type=intf.type,
                    port_status=intf.status.name,
                    tagging=bool(intf.mode != "access"),
                    uuid=intf.id,
                )
                if self.tenant:
                    new_port.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
                self.add(new_port)
                dev = self.get(self.device, intf.device.name)
                dev.add_child(new_port)

    def load_prefixes(self):
        """Load Prefixes from Nautobot into DiffSync models."""
        if self.tenant:
            prefixes = Prefix.objects.filter(tenant=self.tenant)
        else:
            prefixes = Prefix.objects.filter(_custom_field_data__system_of_record="Meraki SSoT")
        for prefix in prefixes:
            new_pf = self.prefix(
                prefix=str(prefix.prefix),
                namespace=prefix.namespace.name,
                tenant=prefix.tenant.name if prefix.tenant else None,
                uuid=prefix.id,
            )
            if getattr(prefix, "locations"):
                for location in prefix.locations.all():
                    pf_loc, loaded = self.get_or_instantiate(
                        self.prefixlocation,
                        ids={"prefix": str(prefix.prefix), "location": location.name},
                        attrs={"uuid": location.id},
                    )
                    if loaded and self.tenant:
                        pf_loc.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
            elif getattr(prefix, "location"):
                pf_loc, loaded = self.get_or_instantiate(
                    self.prefixlocation,
                    ids={"prefix": str(prefix.prefix), "location": prefix.location.name},
                    attrs={"uuid": prefix.location.id},
                )
                if loaded and self.tenant:
                    pf_loc.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
            if self.tenant:
                new_pf.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
            self.add(new_pf)
            self.prefix_map[str(prefix.prefix)] = prefix.id

    def load_ipaddresses(self):
        """Load IPAddresses from Nautobot into DiffSync models."""
        if self.tenant:
            addresses = IPAddress.objects.filter(tenant=self.tenant)
        else:
            addresses = IPAddress.objects.filter(_custom_field_data__system_of_record="Meraki SSoT")
        for ipaddr in addresses:
            if str(ipaddr.parent.namespace) not in self.ipaddr_map:
                self.ipaddr_map[str(ipaddr.parent.namespace)] = {}
            self.ipaddr_map[str(ipaddr.parent.namespace)][str(ipaddr.host)] = ipaddr.id
            new_ip, loaded = self.get_or_instantiate(
                self.ipaddress,
                ids={
                    "host": ipaddr.host,
                    "prefix": str(ipaddr.parent.prefix),
                    "tenant": ipaddr.tenant.name if ipaddr.tenant else None,
                },
                attrs={
                    "mask_length": ipaddr.mask_length,
                    "uuid": ipaddr.id,
                },
            )
            if loaded and self.tenant:
                new_ip.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
            if not loaded:
                self.job.logger.warning(
                    f"Duplicate IP address {ipaddr.host}/{ipaddr.mask_length} {ipaddr.id} found and being skipped."
                )

    def load_ipassignments(self):
        """Load IPAddressToInterface from Nautobot into DiffSync models."""
        if self.tenant:
            mappings = IPAddressToInterface.objects.filter(ip_address__tenant=self.tenant)
        else:
            mappings = IPAddressToInterface.objects.filter(
                ip_address___custom_field_data__system_of_record="Meraki SSoT"
            )
        for ipassignment in mappings:
            if self.job.debug:
                self.job.logger.debug(
                    f"Loading IPAssignment {ipassignment.ip_address.host} on {ipassignment.interface.device.name} "
                    f"port {ipassignment.interface.name} in Namespace {ipassignment.ip_address.parent.namespace.name}"
                )
            new_map = self.ipassignment(
                address=str(ipassignment.ip_address.host),
                namespace=ipassignment.ip_address.parent.namespace.name,
                device=ipassignment.interface.device.name,
                port=ipassignment.interface.name,
                primary=len(ipassignment.ip_address.primary_ip4_for.all()) > 0
                or len(ipassignment.ip_address.primary_ip6_for.all()) > 0,
                uuid=ipassignment.id,
            )
            if self.tenant:
                new_map.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
            self.add(new_map)

    def sync_complete(self, source: Adapter, *args, **kwargs):
        """Clean up function for DiffSync sync.

        Once the sync is complete, this function runs deleting any objects
        from Nautobot that need to be deleted in a specific order.

        Args:
            source (Adapter): Source DiffSync Adapter.
            args (dict): Positional arguments.
            kwargs (dict): Keyword arguments.
        """
        for grouping in (
            "ipaddrs",
            "prefixes",
            "ports",
            "devices",
            "devicetypes",
        ):
            for nautobot_object in self.objects_to_delete[grouping]:
                try:
                    if self.job.debug:
                        self.job.logger.info(f"Deleting {nautobot_object}.")
                    nautobot_object.delete()
                except ProtectedError:
                    self.job.logger.warning(f"Deletion failed protected object: {nautobot_object}")
            self.objects_to_delete[grouping] = []

        self.process_objects_to_create()
        return super().sync_complete(source, *args, **kwargs)

    def process_objects_to_create(self):  # pylint: disable=too-many-branches
        """Process all of the objects that have been added to the objects_to_create dictionary."""
        if len(self.objects_to_create["devicetypes"]) > 0:
            self.job.logger.info("Performing bulk create of DeviceTypes in Nautobot")
            DeviceType.objects.bulk_create(self.objects_to_create["devicetypes"], batch_size=250)
        if len(self.objects_to_create["devices"]) > 0:
            self.job.logger.info("Performing bulk create of Devices in Nautobot")
            Device.objects.bulk_create(self.objects_to_create["devices"], batch_size=250)
        if len(self.objects_to_create["ports"]) > 0:
            self.job.logger.info("Performing bulk create of Interfaces in Nautobot")
            Interface.objects.bulk_create(self.objects_to_create["ports"], batch_size=250)
        if len(self.objects_to_create["prefixes"]) > 0:
            self.job.logger.info("Performing bulk create of Prefixes in Nautobot")
            Prefix.objects.bulk_create(self.objects_to_create["prefixes"], batch_size=250)
        if len(self.objects_to_create["prefix_locs"]) > 0:
            self.job.logger.info("Performing bulk create of PrefixLocationAssignments in Nautobot")
            PrefixLocationAssignment.objects.bulk_create(self.objects_to_create["prefix_locs"], batch_size=250)
        if len(self.objects_to_create["ipaddrs"]) > 0:
            self.job.logger.info("Performing bulk create of IP Addresses in Nautobot")
            IPAddress.objects.bulk_create(self.objects_to_create["ipaddrs"], batch_size=250)
        if len(self.objects_to_create["ipaddrs-to-prefixes"]) > 0:
            self.job.logger.info("Assigning parent Prefix to IPAddresses with bulk_update.")
            assigned_parents = []
            for pair in self.objects_to_create["ipaddrs-to-prefixes"]:
                ipaddr = pair[0]
                ipaddr.parent_id = pair[1]
                assigned_parents.append(ipaddr)
            IPAddress.objects.bulk_update(assigned_parents, ["parent_id"], batch_size=250)
        if len(self.objects_to_create["ipaddrs-to-intfs"]) > 0:
            self.job.logger.info("Performing assignment of IPAddress to Port.")
            IPAddressToInterface.objects.bulk_create(self.objects_to_create["ipaddrs-to-intfs"], batch_size=250)
        if len(self.objects_to_create["device_primary_ip4"]) > 0:
            self.job.logger.info("Performing bulk update of IPv4 addresses in Nautobot.")
            device_primary_ip_objs = []
            for devip in self.objects_to_create["device_primary_ip4"]:
                dev = Device.objects.get(id=devip[0])
                dev.primary_ip4_id = devip[1]
                device_primary_ip_objs.append(dev)
            Device.objects.bulk_update(device_primary_ip_objs, ["primary_ip4_id"], batch_size=250)
        if len(self.objects_to_create["device_primary_ip6"]) > 0:
            self.job.logger.info("Performing bulk update of IPv6 addresses in Nautobot.")
            device_primary_ip_objs = []
            for devip in self.objects_to_create["device_primary_ip6"]:
                dev = Device.objects.get(id=devip[0])
                dev.primary_ip6_id = devip[1]
                device_primary_ip_objs.append(dev)
            Device.objects.bulk_update(device_primary_ip_objs, ["primary_ip6_id"], batch_size=250)
        if len(self.objects_to_create["notes"]) > 0:
            self.job.logger.info("Performing bulk create of Notes in Nautobot")
            Note.objects.bulk_create(self.objects_to_create["notes"], batch_size=250)

    def load(self):
        """Load data from Nautobot into DiffSync models."""
        if self.job.tenant:
            Namespace.objects.get_or_create(name=self.job.tenant.name)
        if self.job.hostname_mapping and len(self.job.hostname_mapping) > 0:
            for mapping in self.job.hostname_mapping:
                new_role, _ = Role.objects.get_or_create(name=mapping[1])
                new_role.content_types.add(ContentType.objects.get_for_model(Device))
        if self.job.devicetype_mapping and len(self.job.devicetype_mapping) > 0:
            for mapping in self.job.devicetype_mapping:
                new_role, _ = Role.objects.get_or_create(name=mapping[1])
                new_role.content_types.add(ContentType.objects.get_for_model(Device))
        self.status_map = {s.name: s.id for s in Status.objects.only("id", "name")}
        self.locationtype_map = {lt.name: lt.id for lt in LocationType.objects.only("id", "name")}
        self.platform_map = {p.name: p.id for p in Platform.objects.only("id", "name")}
        self.manufacturer_map = {m.name: m.id for m in Manufacturer.objects.only("id", "name")}
        self.devicerole_map = {d.name: d.id for d in Role.objects.only("id", "name")}
        self.namespace_map = {ns.name: ns.id for ns in Namespace.objects.only("id", "name")}
        self.contenttype_map = {c.model: c.id for c in ContentType.objects.only("id", "model")}

        if self.job.parent_location:
            self.region_map[self.job.parent_location.name] = self.job.parent_location.id
        else:
            self.region_map = {
                loc_data["parent"]: Location.objects.get(
                    name=loc_data["parent"], location_type=self.job.network_loctype.parent.location_type
                ).id
                for _, loc_data in self.job.location_map.items()
            }
        self.tenant_map = {t.name: t.id for t in Tenant.objects.only("id", "name")}

        self.load_sites()
        self.load_devicetypes()
        self.load_softwareversions()
        self.load_devices()
        self.load_ports()
        self.load_prefixes()
        self.load_ipaddresses()
        self.load_ipassignments()
