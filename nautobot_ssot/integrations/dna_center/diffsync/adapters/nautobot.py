"""Nautobot Adapter for DNA Center SSoT plugin."""

try:
    from nautobot_device_lifecycle_mgmt.models import SoftwareLCM  # noqa: F401

    LIFECYCLE_MGMT = True
except ImportError:
    LIFECYCLE_MGMT = False

from collections import defaultdict
from typing import Optional
from diffsync import DiffSync
from diffsync.enum import DiffSyncModelFlags
from diffsync.exceptions import ObjectNotFound
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.db.utils import IntegrityError
from nautobot.dcim.models import Device as OrmDevice
from nautobot.dcim.models import Interface as OrmInterface
from nautobot.dcim.models import Location as OrmLocation
from nautobot.dcim.models import LocationType as OrmLocationType
from nautobot.extras.models import Status as OrmStatus
from nautobot.extras.models import Relationship as OrmRelationship
from nautobot.extras.models import RelationshipAssociation as OrmRelationshipAssociation
from nautobot.ipam.models import IPAddress as OrmIPAddress
from nautobot.ipam.models import IPAddressToInterface as OrmIPAddressToInterface
from nautobot.ipam.models import Namespace
from nautobot.ipam.models import Prefix as OrmPrefix
from nautobot.tenancy.models import Tenant as OrmTenant
from nautobot_ssot.jobs.base import DataTarget
from nautobot_ssot_dna_center.diffsync.models.nautobot import (
    NautobotArea,
    NautobotBuilding,
    NautobotDevice,
    NautobotFloor,
    NautobotIPAddress,
    NautobotPort,
    NautobotPrefix,
    NautobotIPAddressOnInterface,
)


class NautobotAdapter(DiffSync):
    """DiffSync adapter for Nautobot."""

    area = NautobotArea
    building = NautobotBuilding
    floor = NautobotFloor
    device = NautobotDevice
    port = NautobotPort
    prefix = NautobotPrefix
    ipaddress = NautobotIPAddress
    ip_on_intf = NautobotIPAddressOnInterface

    top_level = ["area", "building", "device", "prefix", "ipaddress", "ip_on_intf"]

    tenant_map = {}
    status_map = {}
    locationtype_map = {}
    region_map = {}
    site_map = {}
    floor_map = {}
    device_map = {}
    port_map = {}
    namespace_map = {}
    prefix_map = {}
    ipaddr_map = {}

    def __init__(
        self, *args, job: Optional[DataTarget] = None, sync=None, tenant: Optional[OrmTenant] = None, **kwargs
    ):
        """Initialize Nautobot.

        Args:
            job (DataTarget, optional): Nautobot job. Defaults to None.
            sync (object, optional): Nautobot DiffSync. Defaults to None.
            tenant (OrmTenant, optional): Tenant defined in Job form that all non-location objects should belong to.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.tenant = tenant
        self.objects_to_create = defaultdict(list)
        self.objects_to_delete = defaultdict(list)

    def load_regions(self):
        """Load Region data from Nautobt into DiffSync models."""
        try:
            loc_type = OrmLocationType.objects.get(name="Region")
            locations = OrmLocation.objects.filter(location_type=loc_type)
            for region in locations:
                self.region_map[region.name] = region.id
                try:
                    self.get(self.area, {"name": region.name, "parent": region.parent.name if region.parent else None})
                    self.job.logger.warning(f"Region {region.name} already loaded so skipping duplicate.")
                except ObjectNotFound:
                    new_region = self.area(
                        name=region.name,
                        parent=region.parent.name if region.parent else None,
                        uuid=region.id,
                    )
                    self.add(new_region)
        except OrmLocationType.DoesNotExist as err:
            self.job.logger.warning(
                f"Unable to find LocationType: Region so can't find region Locations to load. {err}"
            )

    def load_sites(self):
        """Load Site data from Nautobot into DiffSync models."""
        try:
            loc_type = OrmLocationType.objects.get(name="Site")
            locations = OrmLocation.objects.filter(location_type=loc_type)
            for site in locations:
                self.site_map[site.name] = site.id
                try:
                    self.get(self.building, {"name": site.name, "area": site.parent.name if site.parent else None})
                except ObjectNotFound:
                    new_building = self.building(
                        name=site.name,
                        address=site.physical_address,
                        area=site.parent.name if site.parent else "",
                        latitude=str(site.latitude).rstrip("0"),
                        longitude=str(site.longitude).rstrip("0"),
                        tenant=site.tenant.name if site.tenant else None,
                        uuid=site.id,
                    )
                    self.add(new_building)
        except OrmLocationType.DoesNotExist as err:
            self.job.logger.warning(f"Unable to find LocationType: Site so can't find site Locations to load. {err}")

    def load_floors(self):
        """Load LocationType floors from Nautobot into DiffSync models."""
        try:
            loc_type = OrmLocationType.objects.get(name="Floor")
            locations = OrmLocation.objects.filter(location_type=loc_type)
            for location in locations:
                self.floor_map[location.name] = location.id
                new_floor = self.floor(
                    name=location.name,
                    building=location.parent.name if location.parent else "",
                    tenant=location.tenant.name if location.tenant else None,
                    uuid=location.id,
                )
                self.add(new_floor)
                try:
                    if location.parent:
                        building = self.get(self.building, location.parent.name)
                        building.add_child(new_floor)
                except ObjectNotFound as err:
                    self.job.logger.warning(
                        f"Unable to load building {location.parent.name} for floor {location.name}. {err}"
                    )
        except OrmLocationType.DoesNotExist as err:
            self.job.logger.warning(f"Unable to find LocationType: Floor so can't find floor Locations to load. {err}")

    def load_devices(self):
        """Load Device data from Nautobot into DiffSync models."""
        if self.tenant:
            devices = OrmDevice.objects.filter(tenant=self.tenant)
        else:
            devices = OrmDevice.objects.filter(_custom_field_data__system_of_record="DNA Center")
        for dev in devices:
            self.device_map[dev.name] = dev.id
            version = dev.custom_field_data.get("os_version")
            if LIFECYCLE_MGMT:
                try:
                    soft_lcm = OrmRelationship.objects.get(label="Software on Device")
                    version = OrmRelationshipAssociation.objects.get(
                        relationship=soft_lcm, destination_id=dev.id
                    ).source.version
                except OrmRelationshipAssociation.DoesNotExist:
                    pass
            new_dev = self.device(
                name=dev.name,
                status=dev.status.name,
                role=dev.role.name,
                vendor=dev.device_type.manufacturer.name,
                model=dev.device_type.model,
                site=dev.location.parent.name if dev.location.parent else None,
                floor=dev.location.name if dev.location else None,
                serial=dev.serial,
                version=version,
                platform=dev.platform.network_driver if dev.platform else "",
                tenant=dev.tenant.name if dev.tenant else None,
                uuid=dev.id,
            )
            if self.tenant:
                new_dev.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
            self.add(new_dev)

    def load_ports(self):
        """Load Interface data from Nautobot into DiffSync models."""
        if self.tenant:
            ports = OrmInterface.objects.filter(device__tenant=self.tenant)
        else:
            ports = OrmInterface.objects.filter(device___custom_field_data__system_of_record="DNA Center")
        for port in ports:
            if port.device.name not in self.port_map:
                self.port_map[port.device.name] = {}
            self.port_map[port.device.name][port.name] = port.id
            new_port = self.port(
                name=port.name,
                device=port.device.name,
                description=port.description,
                enabled=port.enabled,
                port_type=port.type,
                port_mode=port.mode,
                mac_addr=str(port.mac_address) if getattr(port, "mac_address") else None,
                mtu=port.mtu if port.mtu else 1500,
                status=port.status.name,
                uuid=port.id,
            )
            if self.tenant:
                new_port.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
            self.add(new_port)
            device = self.get(self.device, port.device.name)
            device.add_child(new_port)

    def load_prefixes(self):
        """Load Prefix data from Nautobot into DiffSync models."""
        if self.tenant:
            prefixes = OrmPrefix.objects.filter(tenant=self.tenant)
        else:
            prefixes = OrmPrefix.objects.filter(_custom_field_data__system_of_record="DNA Center")
        for prefix in prefixes:
            self.prefix_map[str(prefix.prefix)] = prefix.id
            new_prefix = self.prefix(
                prefix=str(prefix.prefix),
                namespace=prefix.namespace.name,
                tenant=prefix.tenant.name if prefix.tenant else None,
                uuid=prefix.id,
            )
            if self.tenant:
                new_prefix.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
            self.add(new_prefix)

    def load_ipaddresses(self):
        """Load IPAddress data from Nautobot into DiffSync models."""
        if self.tenant:
            addresses = OrmIPAddress.objects.filter(tenant=self.tenant)
        else:
            addresses = OrmIPAddress.objects.filter(_custom_field_data__system_of_record="DNA Center")
        for ipaddr in addresses:
            self.ipaddr_map[str(ipaddr.host)] = ipaddr.id
            new_ipaddr = self.ipaddress(
                host=str(ipaddr.host),
                mask_length=ipaddr.mask_length,
                namespace=ipaddr.parent.namespace.name,
                tenant=ipaddr.tenant.name if ipaddr.tenant else None,
                uuid=ipaddr.id,
            )
            if self.tenant:
                new_ipaddr.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
            self.add(new_ipaddr)

    def load_ipaddress_to_interface(self):
        """Load IPAddressonInterface data from Nautobot into DiffSync models."""
        if self.tenant:
            mappings = OrmIPAddressToInterface.objects.filter(ip_address__tenant=self.tenant)
        else:
            mappings = OrmIPAddressToInterface.objects.filter(
                ip_address___custom_field_data__system_of_record="DNA Center"
            )
        for mapping in mappings:
            new_ipaddr_to_interface = self.ip_on_intf(
                host=str(mapping.ip_address.host),
                device=mapping.interface.device.name,
                port=mapping.interface.name,
                primary=bool(
                    len(mapping.ip_address.primary_ip4_for.all()) > 0
                    or len(mapping.ip_address.primary_ip6_for.all()) > 0
                ),
                uuid=mapping.id,
            )
            if self.tenant:
                new_ipaddr_to_interface.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
            self.add(new_ipaddr_to_interface)

    def sync_complete(self, source: DiffSync, *args, **kwargs):
        """Label and clean up function for DiffSync sync.

        Once the sync is complete, this function labels all imported objects and then
        deletes any objects from Nautobot that need to be deleted in a specific order.

        Args:
            source (DiffSync): DiffSync
        """
        for grouping in ["ipaddresses", "prefixes", "ports", "devices", "floors", "sites", "regions"]:
            for nautobot_obj in self.objects_to_delete[grouping]:
                try:
                    self.job.logger.info(f"Deleting {nautobot_obj}.")
                    nautobot_obj.delete()
                except ProtectedError:
                    self.job.logger.info(f"Deletion failed protected object: {nautobot_obj}")
            self.objects_to_delete[grouping] = []

        if self.job.bulk_import:
            self.bulk_create_update()
        else:
            self.update_database()
        return super().sync_complete(source, *args, **kwargs)

    def update_database(self):
        """Perform databse update using normal operations."""
        for obj_type in [
            "devices",
            "interfaces",
            "mappings",
        ]:
            if len(self.objects_to_create[obj_type]) > 0:
                self.job.logger.info(f"Importing {len(self.objects_to_create[obj_type])} {obj_type} into Nautobot.")
                for nautobot_obj in self.objects_to_create[obj_type]:
                    try:
                        self.job.logger.info(f"Saving {nautobot_obj}.")
                        nautobot_obj.validated_save()
                    except ValidationError as err:
                        self.job.logger.warning(f"Unable to save {nautobot_obj}. {err}")
                    except IntegrityError as err:
                        self.job.logger.warning(f"Unable to save {nautobot_obj}. {err}")
        if len(self.objects_to_create["primary_ip4"]) > 0:
            self.job.logger.info("Performing assignment of device management IPv4 addresses in Nautobot.")
            for _dev in self.objects_to_create["primary_ip4"]:
                try:
                    dev = OrmDevice.objects.get(id=_dev[0])
                    dev.primary_ip4_id = _dev[1]
                    dev.validated_save()
                except OrmDevice.DoesNotExist as err:
                    self.job.logger.warning(f"Unable to find Device ID {_dev[0]}. {err}")
                except ValidationError as err:
                    self.job.logger.warning(f"Unable to save Device {dev.name}. {err}")
        if len(self.objects_to_create["primary_ip6"]) > 0:
            self.job.logger.info("Performing assignment of device management IPv6 addresses in Nautobot.")
            for _dev in self.objects_to_create["primary_ip6"]:
                try:
                    dev = OrmDevice.objects.get(id=_dev[0])
                    dev.primary_ip6_id = _dev[1]
                    dev.validated_save()
                except OrmDevice.DoesNotExist as err:
                    self.job.logger.warning(f"Unable to find Device ID {_dev[0]}. {err}")
                except ValidationError as err:
                    self.job.logger.warning(f"Unable to save Device {dev.name}. {err}")

    def bulk_create_update(self):
        """Perform database update using bulk operations."""
        if len(self.objects_to_create["devices"]) > 0:
            self.job.logger.info("Performing bulk create of Devices in Nautobot")
            OrmDevice.objects.bulk_create(self.objects_to_create["devices"], batch_size=250)
        if len(self.objects_to_create["interfaces"]) > 0:
            self.job.logger.info("Performing bulk create of Interfaces in Nautobot")
            OrmInterface.objects.bulk_create(self.objects_to_create["interfaces"], batch_size=250)
        if len(self.objects_to_create["mappings"]) > 0:
            self.job.logger.info("Performing assignment of IPAddress to Interface.")
            OrmIPAddressToInterface.objects.bulk_create(self.objects_to_create["mappings"], batch_size=250)
        if len(self.objects_to_create["primary_ip4"]) > 0:
            self.job.logger.info("Performing bulk update of device primary IPv4 addresses in Nautobot.")
            device_primary_ip_objs = []
            for d in self.objects_to_create["primary_ip4"]:
                dev = OrmDevice.objects.get(id=d[0])
                dev.primary_ip4_id = d[1]
                device_primary_ip_objs.append(dev)
            OrmDevice.objects.bulk_update(device_primary_ip_objs, ["primary_ip4_id"], batch_size=250)
        if len(self.objects_to_create["primary_ip6"]) > 0:
            self.job.logger.info("Performing bulk update of device primary IPv6 addresses in Nautobot.")
            device_primary_ip_objs = []
            for d in self.objects_to_create["primary_ip6"]:
                dev = OrmDevice.objects.get(id=d[0])
                dev.primary_ip6_id = d[1]
                device_primary_ip_objs.append(dev)
            OrmDevice.objects.bulk_update(device_primary_ip_objs, ["primary_ip6_id"], batch_size=250)

    def load(self):
        """Load data from Nautobot into DiffSync models."""
        self.locationtype_map = {lt.name: lt.id for lt in OrmLocationType.objects.only("id", "name")}
        self.status_map = {status.name: status.id for status in OrmStatus.objects.only("id", "name")}
        self.tenant_map = {tenant.name: tenant.id for tenant in OrmTenant.objects.only("id", "name")}
        self.namespace_map = {ns.name: ns.id for ns in Namespace.objects.only("id", "name")}

        self.load_regions()
        self.load_sites()
        self.load_floors()
        self.load_devices()
        self.load_ports()
        self.load_prefixes()
        self.load_ipaddresses()
        self.load_ipaddress_to_interface()
