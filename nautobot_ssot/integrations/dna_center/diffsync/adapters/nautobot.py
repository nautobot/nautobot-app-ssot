"""Nautobot Adapter for DNA Center SSoT plugin."""

from collections import defaultdict
from typing import Optional

from diffsync import Adapter
from diffsync.enum import DiffSyncModelFlags
from diffsync.exceptions import ObjectAlreadyExists, ObjectNotFound
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.db.utils import IntegrityError
from nautobot.dcim.models import Device as OrmDevice
from nautobot.dcim.models import Interface as OrmInterface
from nautobot.dcim.models import Location as OrmLocation
from nautobot.dcim.models import LocationType as OrmLocationType
from nautobot.dcim.models import Platform
from nautobot.extras.models import Relationship as OrmRelationship
from nautobot.extras.models import RelationshipAssociation as OrmRelationshipAssociation
from nautobot.extras.models import Status as OrmStatus
from nautobot.ipam.models import IPAddress as OrmIPAddress
from nautobot.ipam.models import IPAddressToInterface as OrmIPAddressToInterface
from nautobot.ipam.models import Namespace
from nautobot.ipam.models import Prefix as OrmPrefix
from nautobot.tenancy.models import Tenant as OrmTenant

from nautobot_ssot.integrations.dna_center.constants import PLUGIN_CFG
from nautobot_ssot.integrations.dna_center.diffsync.models.nautobot import (
    NautobotArea,
    NautobotBuilding,
    NautobotDevice,
    NautobotFloor,
    NautobotIPAddress,
    NautobotIPAddressOnInterface,
    NautobotPort,
    NautobotPrefix,
)
from nautobot_ssot.utils import dlm_supports_softwarelcm

try:
    from nautobot.extras.models.metadata import ObjectMetadata  # noqa: F401

    from nautobot_ssot.integrations.metadata_utils import object_has_metadata

    METADATA_FOUND = True
except (ImportError, RuntimeError):
    METADATA_FOUND = False


class NautobotAdapter(Adapter):
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
    platform_map = {}
    port_map = {}
    namespace_map = {}
    prefix_map = {}
    ipaddr_map = {}

    def __init__(self, *args, job, sync=None, tenant: Optional[OrmTenant] = None, **kwargs):
        """Initialize Nautobot.

        Args:
            job (DataSource): Nautobot job.
            sync (object, optional): Nautobot DiffSync. Defaults to None.
            tenant (OrmTenant, optional): Tenant defined in Job form that all non-location objects should belong to.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.tenant = tenant
        self.objects_to_create = defaultdict(list)
        self.objects_to_delete = defaultdict(list)

    def load_areas(self):
        """Load Location data from Nautobot for specified Area LocationType into DiffSync models."""
        areas = OrmLocation.objects.filter(location_type=self.job.area_loctype).select_related("parent")
        for area in areas:
            parent, parent_of_parent = None, None
            if area.parent:
                parent = area.parent.name
                if area.parent.parent:
                    parent_of_parent = area.parent.parent.name
            if parent not in self.region_map:
                self.region_map[parent] = {}
            self.region_map[parent][area.name] = area.id
            try:
                self.get(self.area, {"name": area.name, "parent": parent, "parent_of_parent": parent_of_parent})
                self.job.logger.warning(
                    f"{self.job.area_loctype.name} {area.name} already loaded so skipping duplicate."
                )
            except ObjectNotFound:
                new_region = self.area(
                    name=area.name,
                    parent=parent,
                    parent_of_parent=parent_of_parent,
                    uuid=area.id,
                )
                if METADATA_FOUND:
                    new_region.metadata = object_has_metadata(obj=area, integration=self.job.data_source)
                if not PLUGIN_CFG.get("dna_center_delete_locations"):
                    new_region.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
                self.add(new_region)

    def load_buildings(self):
        """Load Location data from Nautobot for specified Building LocationType into DiffSync models."""
        buildings = OrmLocation.objects.filter(location_type=self.job.building_loctype)
        for building in buildings:
            if building.parent.name not in self.site_map:
                self.site_map[building.parent.name] = {}
            self.site_map[building.parent.name][building.name] = building.id
            try:
                self.get(
                    self.building,
                    {
                        "name": building.name,
                        "area": building.parent.name if building.parent else None,
                    },
                )
            except ObjectNotFound:
                new_building = self.building(
                    name=building.name,
                    address=building.physical_address,
                    area=building.parent.name if building.parent else "",
                    area_parent=building.parent.parent.name if building.parent and building.parent.parent else None,
                    latitude=str(building.latitude).rstrip("0"),
                    longitude=str(building.longitude).rstrip("0"),
                    tenant=building.tenant.name if building.tenant else None,
                    uuid=building.id,
                )
                if METADATA_FOUND:
                    new_building.metadata = object_has_metadata(obj=building, integration=self.job.data_source)
                if not PLUGIN_CFG.get("dna_center_delete_locations"):
                    new_building.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
                self.add(new_building)

    def load_floors(self):
        """Load LocationType floors from Nautobot into DiffSync models."""
        floors = OrmLocation.objects.filter(location_type=self.job.floor_loctype)
        for floor in floors:
            if floor.parent.parent.name not in self.floor_map:
                self.floor_map[floor.parent.parent.name] = {}
            if floor.parent.name not in self.floor_map[floor.parent.parent.name]:
                self.floor_map[floor.parent.parent.name][floor.parent.name] = {}
            self.floor_map[floor.parent.parent.name][floor.parent.name][floor.name] = floor.id
            new_floor = self.floor(
                name=floor.name,
                area=floor.parent.parent.name if floor.parent.parent else "",
                building=floor.parent.name if floor.parent else "",
                tenant=floor.tenant.name if floor.tenant else None,
                uuid=floor.id,
            )
            self.add(new_floor)
            if METADATA_FOUND:
                if object_has_metadata(obj=floor, integration=self.job.data_source):
                    new_floor.metadata = True
            try:
                if floor.parent:
                    building = self.get(
                        self.building,
                        {"name": floor.parent.name, "area": floor.parent.parent.name},
                    )
                    building.add_child(new_floor)
            except ObjectNotFound as err:
                self.job.logger.warning(
                    f"Unable to load {self.job.building_loctype.name} {floor.parent.name} for {self.job.floor_loctype.name} {floor.name}. {err}"
                )

    def load_devices(self):
        """Load Device data from Nautobot into DiffSync models."""
        if self.tenant:
            devices = OrmDevice.objects.filter(tenant=self.tenant)
        else:
            devices = OrmDevice.objects.filter(_custom_field_data__system_of_record="DNA Center")
        for dev in devices:
            self.device_map[dev.name] = dev.id
            version = None
            if getattr(dev, "software_version"):
                version = dev.software_version.version
            if dlm_supports_softwarelcm():
                dlm_version = None
                try:
                    soft_lcm = OrmRelationship.objects.get(label="Software on Device")
                    dlm_version = OrmRelationshipAssociation.objects.get(
                        relationship=soft_lcm, destination_id=dev.id
                    ).source.version
                except OrmRelationship.DoesNotExist:
                    pass
                except OrmRelationshipAssociation.DoesNotExist:
                    pass
                if dlm_version != version:
                    version = None
            bldg_name, floor_name = None, None
            if dev.location.location_type == self.job.floor_loctype:
                floor_name = dev.location.name
                bldg_name = dev.location.parent.name
                area_name = dev.location.parent.parent.name
            if dev.location.location_type == self.job.building_loctype:
                bldg_name = dev.location.name
                area_name = dev.location.parent.name
            new_dev = self.device(
                name=dev.name,
                status=dev.status.name,
                role=dev.role.name,
                vendor=dev.device_type.manufacturer.name,
                model=dev.device_type.model,
                area=area_name,
                site=bldg_name,
                floor=floor_name,
                serial=dev.serial,
                version=version,
                platform=dev.platform.network_driver if dev.platform else "",
                tenant=dev.tenant.name if dev.tenant else None,
                controller_group=(
                    dev.controller_managed_device_group.name if dev.controller_managed_device_group else ""
                ),
                uuid=dev.id,
            )
            if METADATA_FOUND:
                if object_has_metadata(obj=dev, integration=self.job.data_source):
                    new_dev.metadata = True
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
            if METADATA_FOUND:
                if object_has_metadata(obj=port, integration=self.job.data_source):
                    new_port.metadata = True
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
            if METADATA_FOUND:
                if object_has_metadata(obj=prefix, integration=self.job.data_source):
                    new_prefix.metadata = True
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
            if METADATA_FOUND:
                if object_has_metadata(obj=ipaddr, integration=self.job.data_source):
                    new_ipaddr.metadata = True
            if self.tenant:
                new_ipaddr.model_flags = DiffSyncModelFlags.SKIP_UNMATCHED_DST
            try:
                self.add(new_ipaddr)
            except ObjectAlreadyExists:
                self.job.logger.warning(f"IPAddress {ipaddr.host} already loaded so skipping duplicate. {ipaddr.id}")

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

    def sync_complete(self, source: Adapter, *args, **kwargs):
        """Label and clean up function for DiffSync sync.

        Once the sync is complete, this function labels all imported objects and then
        deletes any objects from Nautobot that need to be deleted in a specific order.

        Args:
            source (Adapter): DiffSync
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
        for obj_type in ["devices", "interfaces", "mappings", "metadata"]:
            if len(self.objects_to_create[obj_type]) > 0:
                self.job.logger.info(f"Importing {len(self.objects_to_create[obj_type])} {obj_type} into Nautobot.")
                for nautobot_obj in self.objects_to_create[obj_type]:
                    try:
                        if self.job.debug:
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
        if len(self.objects_to_create["metadata"]) > 0:
            self.job.logger.info("Performing bulk create of ObjectMetadata in Nautobot.")
            ObjectMetadata.objects.bulk_create(self.objects_to_create["metadata"], batch_size=250)
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
        self.platform_map = {
            platform.network_driver: platform.id for platform in Platform.objects.only("id", "network_driver")
        }

        self.load_areas()
        self.load_buildings()
        self.load_floors()
        self.load_devices()
        self.load_ports()
        self.load_prefixes()
        self.load_ipaddresses()
        self.load_ipaddress_to_interface()
