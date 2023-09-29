"""DiffSync adapter class for Nautobot as source-of-truth."""

import ipaddress
from collections import defaultdict

from diffsync import DiffSync
from diffsync.exceptions import ObjectAlreadyExists, ObjectNotFound
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from nautobot.circuits.models import Circuit, CircuitTermination, Provider
from nautobot.dcim.models import (
    Cable,
    Device,
    DeviceRole,
    DeviceType,
    FrontPort,
    Interface,
    Manufacturer,
    Platform,
    Rack,
    RackGroup,
    RearPort,
    Site,
    VirtualChassis,
)
from nautobot.extras.jobs import Job
from nautobot.extras.models import Relationship, RelationshipAssociation, Status
from nautobot.ipam.models import VLAN, VRF, IPAddress, Prefix
from netutils.lib_mapper import ANSIBLE_LIB_MAPPER

from nautobot_ssot.integrations.device42.constant import PLUGIN_CFG
from nautobot_ssot.integrations.device42.diffsync.models.nautobot import assets, circuits, dcim, ipam
from nautobot_ssot.integrations.device42.utils import nautobot

try:
    from nautobot_device_lifecycle_mgmt.models import SoftwareLCM

    LIFECYCLE_MGMT = True
except ImportError:
    print("Device Lifecycle plugin isn't installed so will revert to CustomField for OS version.")
    LIFECYCLE_MGMT = False


class NautobotAdapter(DiffSync):
    """Nautobot adapter for DiffSync."""

    building = dcim.NautobotBuilding
    room = dcim.NautobotRoom
    rack = dcim.NautobotRack
    vendor = dcim.NautobotVendor
    hardware = dcim.NautobotHardware
    cluster = dcim.NautobotCluster
    device = dcim.NautobotDevice
    port = dcim.NautobotPort
    vrf = ipam.NautobotVRFGroup
    subnet = ipam.NautobotSubnet
    ipaddr = ipam.NautobotIPAddress
    vlan = ipam.NautobotVLAN
    conn = dcim.NautobotConnection
    provider = circuits.NautobotProvider
    circuit = circuits.NautobotCircuit
    patchpanel = assets.NautobotPatchPanel
    patchpanelrearport = assets.NautobotPatchPanelRearPort
    patchpanelfrontport = assets.NautobotPatchPanelFrontPort

    top_level = [
        "vrf",
        "subnet",
        "vendor",
        "hardware",
        "building",
        "vlan",
        "cluster",
        "device",
        "patchpanel",
        "patchpanelrearport",
        "patchpanelfrontport",
        "ipaddr",
        "provider",
        "circuit",
        "conn",
    ]

    status_map = {}
    platform_map = {}
    site_map = {}
    room_map = {}
    rack_map = {}
    vendor_map = {}
    devicerole_map = {}
    devicetype_map = {}
    cluster_map = {}
    device_map = {}
    port_map = {}
    vrf_map = {}
    prefix_map = {}
    ipaddr_map = {}
    vlan_map = {}
    circuit_map = {}
    cable_map = {}
    provider_map = {}
    rp_map = {}
    fp_map = {}
    softwarelcm_map = {}
    relationship_map = {}

    def __init__(self, *args, job: Job, sync=None, **kwargs):
        """Initialize the Nautobot DiffSync adapter.

        Args:
            job (Job): Nautobot Job.
            sync (object, optional): Nautobot DiffSync. Defaults to None.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.objects_to_delete = defaultdict(list)
        self.objects_to_create = defaultdict(list)

    def sync_complete(self, source: DiffSync, *args, **kwargs):
        """Clean up function for DiffSync sync.

        Once the sync is complete, this function runs deleting any objects
        from Nautobot that need to be deleted in a specific order.

        Args:
            source (DiffSync): DiffSync
        """
        if PLUGIN_CFG.get("delete_on_sync"):
            for grouping in (
                "ipaddr",
                "subnet",
                "vrf",
                "vlan",
                "circuit",
                "provider",
                "cluster",
                "port",
                "device",
                "patchpanel",
                "device_type",
                "manufacturer",
                "rack",
                "site",
            ):
                for nautobot_object in self.objects_to_delete[grouping]:
                    try:
                        if self.job.kwargs.get("debug"):
                            self.job.log_info(message=f"Deleting {nautobot_object}.")
                        nautobot_object.delete()
                    except ProtectedError:
                        self.job.log(f"Deletion failed protected object: {nautobot_object}")
                self.objects_to_delete[grouping] = []

        if len(self.objects_to_create["sites"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk create of Sites in Nautobot")
                Site.objects.bulk_create(self.objects_to_create["sites"], batch_size=50)
            else:
                self.job.log_info(message="Performing creation of Sites in Nautobot.")
                try:
                    for site in self.objects_to_create["sites"]:
                        site.validated_save()
                except ValidationError as err:
                    self.job.log_warning(message=f"Error with creating site. {err}")
        if len(self.objects_to_create["rooms"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk create of Sites in Nautobot")
                RackGroup.objects.bulk_create(self.objects_to_create["rooms"], batch_size=50)
            else:
                self.job.log_info(message="Performing creation of RackGroups in Nautobot")
                try:
                    for room in self.objects_to_create["rooms"]:
                        room.validated_save()
                except ValidationError as err:
                    self.job.log_warning(message=f"Error with creating room. {err}")
        if len(self.objects_to_create["racks"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk create of Racks in Nautobot")
                Rack.objects.bulk_create(self.objects_to_create["racks"], batch_size=50)
            else:
                self.job.log_info(message="Performing creation of Racks in Nautobot")
                try:
                    for rack in self.objects_to_create["racks"]:
                        rack.validated_save()
                except ValidationError as err:
                    self.job.log_warning(message=f"Error with creating rack. {err}")
        if len(self.objects_to_create["vendors"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk create of Manufacturers in Nautobot")
                Manufacturer.objects.bulk_create(self.objects_to_create["vendors"], batch_size=50)
            else:
                self.job.log_info(message="Performing creation of Manufacturers in Nautobot")
                try:
                    for manu in self.objects_to_create["vendors"]:
                        manu.validated_save()
                except ValidationError as err:
                    self.job.log_warning(message=f"Error with creating manufacturer. {err}")
        if len(self.objects_to_create["devicetypes"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk create of DeviceTypes in Nautobot")
                DeviceType.objects.bulk_create(self.objects_to_create["devicetypes"], batch_size=50)
            else:
                self.job.log_info(message="Performing creation of DeviceTypes in Nautobot")
                try:
                    for _dt in self.objects_to_create["devicetypes"]:
                        _dt.validated_save()
                except ValidationError as err:
                    self.job.log_warning(message=f"Error with creating device type. {err}")
        if len(self.objects_to_create["deviceroles"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk create of DeviceRoles in Nautobot")
                DeviceRole.objects.bulk_create(self.objects_to_create["deviceroles"], batch_size=50)
            else:
                self.job.log_info(message="Performing creation of DeviceRoles in Nautobot")
                try:
                    for role in self.objects_to_create["deviceroles"]:
                        role.validated_save()
                except ValidationError as err:
                    self.job.log_warning(message=f"Error with creating device role. {err}")
        if len(self.objects_to_create["platforms"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk create of Platforms in Nautobot")
                Platform.objects.bulk_create(self.objects_to_create["platforms"], batch_size=50)
            else:
                self.job.log_info(message="Performing creation of Platforms in Nautobot")
                try:
                    for platform in self.objects_to_create["platforms"]:
                        platform.validated_save()
                except ValidationError as err:
                    self.job.log_warning(message=f"Error with creating platform. {err}")
        if len(self.objects_to_create["vrfs"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk create of VRFs in Nautobot")
                VRF.objects.bulk_create(self.objects_to_create["vrfs"], batch_size=50)
            else:
                self.job.log_info(message="Performing creation of VRFs in Nautobot")
                try:
                    for vrf in self.objects_to_create["vrfs"]:
                        vrf.validated_save()
                except ValidationError as err:
                    self.job.log_warning(message=f"Error with creating VRF. {err}")
        if len(self.objects_to_create["vlans"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk create of VLANs in Nautobot")
                VLAN.objects.bulk_create(self.objects_to_create["vlans"], batch_size=50)
            else:
                self.job.log_info(message="Performing creation of VLANs in Nautobot")
                try:
                    for vlan in self.objects_to_create["vlans"]:
                        vlan.validated_save()
                except ValidationError as err:
                    self.job.log_warning(message=f"Error with creating VLAN. {err}")
        if len(self.objects_to_create["prefixes"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk create of Prefixes in Nautobot")
                Prefix.objects.bulk_create(self.objects_to_create["prefixes"], batch_size=50)
            else:
                self.job.log_info(message="Performing creation of Prefixes in Nautobot")
                try:
                    for prefix in self.objects_to_create["prefixes"]:
                        prefix.validated_save()
                except ValidationError as err:
                    self.job.log_warning(message=f"Error with creating VRF. {err}")
        if len(self.objects_to_create["clusters"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk create of Virtual Chassis in Nautobot")
                VirtualChassis.objects.bulk_create(self.objects_to_create["clusters"], batch_size=50)
            else:
                self.job.log_info(message="Performing creation of Virtual Chassis in Nautobot")
                try:
                    for cluster in self.objects_to_create["clusters"]:
                        cluster.validated_save()
                except ValidationError as err:
                    self.job.log_warning(message=f"Error with creating virtual chassis. {err}")
        if len(self.objects_to_create["devices"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk create of Devices in Nautobot")
                Device.objects.bulk_create(self.objects_to_create["devices"], batch_size=50)
            else:
                self.job.log_info(message="Performing creation of Devices in Nautobot")
                try:
                    for dev in self.objects_to_create["devices"]:
                        dev.validated_save()
                except ValidationError as err:
                    self.job.log_warning(message=f"Error with saving device {dev.name}. {err}")
                except VirtualChassis.DoesNotExist as err:
                    self.job.log_warning(message=f"Error with creating device as VirtualChassis doesn't exist. {err}")
        if len(self.objects_to_create["ports"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk create of Interfaces in Nautobot")
                Interface.objects.bulk_create(self.objects_to_create["ports"], batch_size=50)
            else:
                self.job.log_info(message="Performing creation of Interfaces in Nautobot")
                try:
                    for port in self.objects_to_create["ports"]:
                        port.validated_save()
                except ValidationError as err:
                    self.job.log_warning(message=f"Error with creating interface. {err}")
                except Device.DoesNotExist as err:
                    self.job.log_warning(message=f"Error with creating interface as Device doesn't exist. {err}")
        if len(self.objects_to_create["rear_ports"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk create of Rear Ports in Nautobot")
                RearPort.objects.bulk_create(self.objects_to_create["rear_ports"], batch_size=50)
            else:
                self.job.log_info(message="Performing creation of Rear Ports in Nautobot")
                try:
                    for port in self.objects_to_create["rear_ports"]:
                        port.validated_save()
                except ValidationError as err:
                    self.job.log_warning(message=f"Error with creating rear port. {err}")
        if len(self.objects_to_create["front_ports"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk create of Front Ports in Nautobot")
                FrontPort.objects.bulk_create(self.objects_to_create["front_ports"], batch_size=50)
            else:
                self.job.log_info(message="Performing creation of Front Ports in Nautobot")
                try:
                    for port in self.objects_to_create["front_ports"]:
                        port.validated_save()
                except ValidationError as err:
                    self.job.log_warning(message=f"Error with creating front port. {err}")
        if len(self.objects_to_create["ipaddrs"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk create of IP Addresses in Nautobot")
                IPAddress.objects.bulk_create(self.objects_to_create["ipaddrs"], batch_size=50)
            else:
                self.job.log_info(message="Performing creation of IP Addresses in Nautobot")
                try:
                    for ipaddr in self.objects_to_create["ipaddrs"]:
                        ipaddr.validated_save()
                except ValidationError as err:
                    self.job.log_warning(message=f"Error with creating IP address. {err}")
        if len(self.objects_to_create["providers"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk create of Providers in Nautobot")
                Provider.objects.bulk_create(self.objects_to_create["providers"], batch_size=50)
            else:
                self.job.log_info(message="Performing creation of Providers in Nautobot")
                try:
                    for provider in self.objects_to_create["providers"]:
                        provider.validated_save()
                except ValidationError as err:
                    self.job.log_warning(message=f"Error with creating provider. {err}")
        if len(self.objects_to_create["circuits"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk create of Circuits in Nautobot")
                Circuit.objects.bulk_create(self.objects_to_create["circuits"], batch_size=50)
            else:
                self.job.log_info(message="Performing creation of Circuits in Nautobot")
                try:
                    for circuit in self.objects_to_create["circuits"]:
                        circuit.validated_save()
                except ValidationError as err:
                    self.job.log_warning(message=f"Error with creating circuit. {err}")

        # if len(self.objects_to_create["cables"]) > 0:
        #     self.job.log_info(message="Performing bulk create of Cables in Nautobot")
        #     Cable.objects.bulk_create(self.objects_to_create["cables"], batch_size=50)

        if len(self.objects_to_create["device_primary_ip"]) > 0:
            if self.job.kwargs["bulk_import"]:
                self.job.log_info(message="Performing bulk update of device management IP addresses in Nautobot.")
                device_primary_ip4_objs = []
                device_primary_ip6_objs = []
                for d in self.objects_to_create["device_primary_ip"]:
                    dev = Device.objects.get(id=d[0])
                    ipaddr = IPAddress.objects.get(id=d[1])
                    if ipaddr.family == 4:
                        dev.primary_ip4_id = d[1]
                        device_primary_ip4_objs.append(dev)
                    else:
                        dev.primary_ip6_id = d[1]
                        device_primary_ip6_objs.append(dev)
                Device.objects.bulk_update(device_primary_ip4_objs, ["primary_ip4_id"], batch_size=50)
                Device.objects.bulk_update(device_primary_ip6_objs, ["primary_ip6_id"], batch_size=50)
            else:
                self.job.log_info(message="Performing assignment of device management IP addresses in Nautobot")
                for dev_ip in self.objects_to_create["device_primary_ip"]:
                    dev, ipaddr = None, None
                    try:
                        dev = Device.objects.get(id=dev_ip[0])
                    except Device.DoesNotExist as err:
                        self.job.log_warning(
                            message=f"Unable to find Device {dev_ip[0].name} to assign primary IP. {err}"
                        )
                    try:
                        ipaddr = IPAddress.objects.get(id=dev_ip[1])
                        ipaddr.validated_save()
                        try:
                            if dev and ipaddr:
                                if ipaddr.assigned_object.device == dev:
                                    if ipaddr.family == 4:
                                        dev.primary_ip4_id = dev_ip[1]
                                    else:
                                        dev.primary_ip6_id = dev_ip[1]
                                    dev.validated_save()
                                else:
                                    self.job.log_warning(
                                        message=f"IP Address doesn't show assigned to {dev} so can't mark primary."
                                    )
                        except ValidationError as err:
                            self.job.log_warning(message=f"Unable to assign primary IP to {dev}. {err}")
                    except IPAddress.DoesNotExist as err:
                        self.job.log_warning(
                            message=f"Unable to find IP Address {dev_ip[1].address} to assign primary IP. {err}"
                        )
                    except ValidationError as err:
                        self.job.log_warning(message=f"Unable to save IP Address {dev_ip[1]} for {dev}. {err}")

        if len(self.objects_to_create["master_devices"]) > 0:
            master_devices = []
            self.job.log_info(message="Performing assignment of master devices to Virtual Chassis in Nautobot")
            for item in self.objects_to_create["master_devices"]:
                new_vc = VirtualChassis.objects.get(id=item[0])
                new_vc.master = Device.objects.get(id=item[1])
                if self.job.kwargs["bulk_import"]:
                    master_devices.append(new_vc)
                else:
                    new_vc.validated_save()
            if self.job.kwargs["bulk_import"]:
                VirtualChassis.objects.bulk_update(master_devices, ["master"], batch_size=50)

        if len(self.objects_to_create["tagged_vlans"]) > 0:
            self.job.log_info(message="Assigning tagged VLANs to Ports in Nautobot.")
            for item in self.objects_to_create["tagged_vlans"]:
                port, tagged_vlans = item
                port.tagged_vlans.set(tagged_vlans)
                port.validated_save()

        if LIFECYCLE_MGMT:
            if len(self.objects_to_create["softwarelcms"]) > 0:
                if self.job.kwargs["bulk_import"]:
                    self.job.log_info(
                        message="Performing bulk creation of Software Versions in Device Lifecycle plugin."
                    )
                    SoftwareLCM.objects.bulk_create(self.objects_to_create["softwarelcms"], batch_size=50)
                else:
                    self.job.log_info(message="Performing creation of Software Versions in Device Lifecycle plugin.")
                    try:
                        for softwarelcm in self.objects_to_create["softwarelcms"]:
                            softwarelcm.validated_save()
                    except ValidationError as err:
                        self.job.log_warning(message=f"Error with creating software version. {err}")
            if len(self.objects_to_create["relationshipasscs"]) > 0:
                if self.job.kwargs["bulk_import"]:
                    self.job.log_info(message="Creating Relationships between Devices and Software Versions.")
                    RelationshipAssociation.objects.bulk_create(
                        self.objects_to_create["relationshipasscs"], batch_size=50
                    )
                else:
                    self.job.log_info(
                        message="Performing creation of Relationships between Devices and Software Versions."
                    )
                    try:
                        for assc in self.objects_to_create["relationshipasscs"]:
                            assc.validated_save()
                    except ValidationError as err:
                        self.job.log_warning(
                            message=f"Error with creating relationships between device and software version. {err}"
                        )
        return super().sync_complete(source, *args, **kwargs)

    def load_sites(self):
        """Add Nautobot Site objects as DiffSync Building models."""
        for site in Site.objects.all():
            self.site_map[site.slug] = site.id
            try:
                building = self.building(
                    name=site.name,
                    address=site.physical_address,
                    latitude=site.latitude,
                    longitude=site.longitude,
                    contact_name=site.contact_name,
                    contact_phone=site.contact_phone,
                    tags=nautobot.get_tag_strings(site.tags),
                    custom_fields=nautobot.get_custom_field_dict(site.get_custom_fields()),
                    uuid=site.id,
                )
                self.add(building)
            except AttributeError:
                continue

    def load_rackgroups(self):
        """Add Nautobot RackGroup objects as DiffSync Room models."""
        for _rg in RackGroup.objects.select_related("site").all():
            if _rg.site.slug not in self.room_map:
                self.room_map[_rg.site.slug] = {}
            if _rg.slug not in self.room_map[_rg.site.slug]:
                self.room_map[_rg.site.slug][_rg.slug] = {}
            self.room_map[_rg.site.slug][_rg.slug] = _rg.id
            room = self.room(
                name=_rg.name,
                building=Site.objects.get(name=_rg.site).name,
                notes=_rg.description,
                custom_fields=nautobot.get_custom_field_dict(_rg.get_custom_fields()),
                uuid=_rg.id,
            )
            self.add(room)
            _site = self.get(self.building, Site.objects.get(name=_rg.site).name)
            _site.add_child(child=room)

    def load_racks(self):
        """Add Nautobot Rack objects as DiffSync Rack models."""
        for rack in Rack.objects.select_related("site", "group").all():
            if rack.site.slug not in self.rack_map:
                self.rack_map[rack.site.slug] = {}
            if rack.group.slug not in self.rack_map[rack.site.slug]:
                self.rack_map[rack.site.slug][rack.group.slug] = {}
            if rack.name not in self.rack_map[rack.site.slug][rack.group.slug]:
                self.rack_map[rack.site.slug][rack.group.slug][rack.name] = {}
            self.rack_map[rack.site.slug][rack.group.slug][rack.name] = rack.id
            try:
                new_rack = self.rack(
                    name=rack.name,
                    building=rack.site.name,
                    room=rack.group.name,
                    height=rack.u_height,
                    numbering_start_from_bottom="no" if rack.desc_units else "yes",
                    tags=nautobot.get_tag_strings(rack.tags),
                    custom_fields=nautobot.get_custom_field_dict(rack.get_custom_fields()),
                    uuid=rack.id,
                )
                self.add(new_rack)
                _room = self.get(self.room, {"name": rack.group, "building": rack.site.name})
                _room.add_child(child=new_rack)
            except ObjectAlreadyExists as err:
                if self.job.kwargs.get("debug"):
                    self.job.log_warning(message=err)

    def load_manufacturers(self):
        """Add Nautobot Manufacturer objects as DiffSync Vendor models."""
        for manu in Manufacturer.objects.all():
            self.vendor_map[manu.slug] = manu.id
            new_manu = self.vendor(
                name=manu.name,
                custom_fields=nautobot.get_custom_field_dict(manu.get_custom_fields()),
                uuid=manu.id,
            )
            self.add(new_manu)

    def load_device_types(self):
        """Add Nautobot DeviceType objects as DiffSync Hardware models."""
        for _dt in DeviceType.objects.select_related("manufacturer").all():
            self.devicetype_map[_dt.slug] = _dt.id
            dtype = self.hardware(
                name=_dt.model,
                manufacturer=_dt.manufacturer.name,
                size=_dt.u_height,
                depth="Full Depth" if _dt.is_full_depth else "Half Depth",
                part_number=_dt.part_number,
                custom_fields=nautobot.get_custom_field_dict(_dt.get_custom_fields()),
                uuid=_dt.id,
            )
            self.add(dtype)

    def load_virtual_chassis(self):
        """Add Nautobot Virtual Chassis objects as DiffSync."""
        # We import the master node as a VC
        for _vc in VirtualChassis.objects.all():
            self.cluster_map[_vc.name] = _vc.id
            _members = [x.name for x in _vc.members.all() if x.name != _vc.name]
            if len(_members) > 1:
                _members.sort()
            new_vc = self.cluster(
                name=_vc.name,
                members=_members,
                tags=nautobot.get_tag_strings(_vc.tags),
                custom_fields=nautobot.get_custom_field_dict(_vc.get_custom_fields()),
                uuid=_vc.id,
            )
            self.add(new_vc)

    def load_devices(self):
        """Add Nautobot Device objects as DiffSync Device models."""
        for dev in Device.objects.select_related(
            "status", "device_type", "device_role", "site", "rack", "platform", "vc_master_for", "virtual_chassis"
        ).all():
            self.device_map[dev.name] = dev.id
            # As patch panels are added as Devices, we need to filter them out for their own load method.
            if DeviceRole.objects.get(id=dev.device_role.id).name == "patch panel":
                patch_panel = self.patchpanel(
                    name=dev.name,
                    in_service=bool(str(dev.status.name) == "Active"),
                    vendor=dev.device_type.manufacturer.name,
                    model=dev.device_type.model,
                    size=dev.device_type.u_height,
                    position=dev.position,
                    orientation=dev.face if dev.face else "rear",
                    num_ports=len(FrontPort.objects.filter(device__name=dev.name)),
                    building=dev.site.slug,
                    room=dev.rack.group.name if dev.rack else None,
                    rack=dev.rack.name if dev.rack else None,
                    serial_no=dev.serial if dev.serial else "",
                    uuid=dev.id,
                )
                self.add(patch_panel)
                continue
            if dev.platform and dev.platform.name in ANSIBLE_LIB_MAPPER:
                _platform = ANSIBLE_LIB_MAPPER[dev.platform.name]
            elif dev.platform:
                _platform = dev.platform.name
            else:
                _platform = ""
            if LIFECYCLE_MGMT:
                _version = nautobot.get_software_version_from_lcm(relations=dev.get_relationships())
            else:
                _version = nautobot.get_version_from_custom_field(fields=dev.get_custom_fields())
            _dev = self.device(
                name=dev.name,
                building=dev.site.slug,
                room=dev.rack.group.name if dev.rack else "",
                rack=dev.rack.name if dev.rack else "",
                rack_position=dev.position,
                rack_orientation=dev.face if dev.face else "rear",
                hardware=dev.device_type.model,
                os=_platform,
                os_version=_version,
                in_service=bool(str(dev.status) == "Active"),
                serial_no=dev.serial if dev.serial else "",
                tags=nautobot.get_tag_strings(dev.tags),
                master_device=False,
                custom_fields=nautobot.get_custom_field_dict(dev.get_custom_fields()),
                uuid=dev.id,
                cluster_host=None,
                vc_position=dev.vc_position,
            )
            if dev.virtual_chassis:
                _dev.cluster_host = str(dev.virtual_chassis)
                if hasattr(dev, "vc_master_for"):
                    if str(dev.vc_master_for) == _dev.cluster_host:
                        _dev.master_device = True
            self.add(_dev)

    def load_interfaces(self):
        """Add Nautobot Interface objects as DiffSync Port models."""
        for port in Interface.objects.select_related("device", "status").all():
            if port.device.name not in self.port_map:
                self.port_map[port.device.name] = {}
            if port.name not in self.port_map[port.device.name]:
                self.port_map[port.device.name][port.name] = {}
            self.port_map[port.device.name][port.name] = port.id
            if port.mac_address:
                _mac_addr = str(port.mac_address).replace(":", "").lower()
                self.port_map[_mac_addr[:12]] = port.id
            else:
                _mac_addr = ""
            try:
                _port = self.get(self.port, {"device": port.device.name, "name": port.name})
            except ObjectNotFound:
                if self.job.kwargs.get("debug"):
                    self.job.log_debug(message=f"Loading Interface: {port.name} for {port.device}.")
                _port = self.port(
                    name=port.name,
                    device=port.device.name,
                    enabled=port.enabled,
                    mtu=port.mtu,
                    description=port.description,
                    mac_addr=_mac_addr[:13],
                    type=port.type,
                    tags=nautobot.get_tag_strings(port.tags),
                    mode=port.mode if port.mode else "access",
                    status=port.status.slug if hasattr(port, "status") else "active",
                    vlans=[],
                    custom_fields=nautobot.get_custom_field_dict(port.get_custom_fields()),
                    uuid=port.id,
                )
                if port.mode == "access" and port.untagged_vlan:
                    _port.vlans = [port.untagged_vlan.vid]
                else:
                    _vlans = []
                    for _vlan in port.tagged_vlans.values():
                        _vlans.append(_vlan["vid"])
                    _port.vlans = sorted(set(_vlans))
                self.add(_port)
                _dev = self.get(self.device, port.device.name)
                _dev.add_child(_port)

    def load_vrfs(self):
        """Add Nautobot VRF objects as DiffSync VRFGroup models."""
        for vrf in VRF.objects.all():
            self.vrf_map[vrf.name] = vrf.id
            if self.job.kwargs.get("debug"):
                self.job.log_debug(message=f"Loading VRF: {vrf.name}.")
            _vrf = self.vrf(
                name=vrf.name,
                description=vrf.description,
                tags=nautobot.get_tag_strings(vrf.tags),
                custom_fields=nautobot.get_custom_field_dict(vrf.get_custom_fields()),
                uuid=vrf.id,
            )
            self.add(_vrf)

    def load_prefixes(self):
        """Add Nautobot Prefix objects as DiffSync Subnet models."""
        for _pf in Prefix.objects.select_related("vrf").all():
            if _pf.vrf:
                vrf_name = _pf.vrf.name
            else:
                vrf_name = "unknown"
            if vrf_name not in self.prefix_map:
                self.prefix_map[vrf_name] = {}
            self.prefix_map[vrf_name][str(_pf.prefix)] = _pf.id
            if self.job.kwargs.get("debug"):
                self.job.log_debug(message=f"Loading Prefix: {_pf.prefix}.")
            ip_net = ipaddress.ip_network(_pf.prefix)
            new_pf = self.subnet(
                network=str(ip_net.network_address),
                mask_bits=ip_net.prefixlen,
                description=_pf.description,
                vrf=_pf.vrf.name,
                tags=nautobot.get_tag_strings(_pf.tags),
                custom_fields=nautobot.get_custom_field_dict(_pf.get_custom_fields()),
                uuid=_pf.id,
            )
            self.add(new_pf)

    def load_ip_addresses(self):
        """Add Nautobot IPAddress objects as DiffSync IPAddress models."""
        for _ip in IPAddress.objects.select_related("status", "vrf").all():
            if _ip.vrf:
                vrf_name = _ip.vrf.name
            else:
                vrf_name = "global"
            if vrf_name not in self.ipaddr_map:
                self.ipaddr_map[vrf_name] = {}
            if str(_ip.address) not in self.ipaddr_map[vrf_name]:
                self.ipaddr_map[vrf_name][str(_ip.address)] = {}
            self.ipaddr_map[vrf_name][str(_ip.address)] = _ip.id
            if self.job.kwargs.get("debug"):
                self.job.log_debug(message=f"Loading IPAddress: {_ip.address}.")
            new_ip = self.ipaddr(
                address=str(_ip.address),
                available=bool(_ip.status.name != "Active"),
                label=_ip.description,
                vrf=_ip.vrf.name if _ip.vrf else None,
                tags=nautobot.get_tag_strings(_ip.tags),
                interface="",
                device="",
                custom_fields=nautobot.get_custom_field_dict(_ip.get_custom_fields()),
                uuid=_ip.id,
                primary=None,
            )
            if _ip.assigned_object_id:
                try:
                    _intf = Interface.objects.get(id=_ip.assigned_object_id)
                    new_ip.interface = _intf.name
                    new_ip.device = _intf.device.name
                except Interface.DoesNotExist:
                    _ip.assigned_object_id = None
                    _ip.assigned_object_type = None
                    if self.job.kwargs.get("debug"):
                        self.job.log_warning(
                            message=f"Can't find assigned Interface {_ip.assigned_object_id} for {_ip.address}. Removing assignment."
                        )
            if hasattr(_ip, "primary_ip4_for") or hasattr(_ip, "primary_ip6_for"):
                new_ip.primary = True
            else:
                new_ip.primary = False
            try:
                self.add(new_ip)
            except ObjectAlreadyExists as err:
                if self.job.kwargs.get("debug"):
                    self.job.log_debug(
                        message=f"Duplicate IP Address {_ip.address} found and won't be imported. Validate the duplicate address is accurate. {err}"
                    )

    def load_vlans(self):
        """Add Nautobot VLAN objects as DiffSync VLAN models."""
        for vlan in VLAN.objects.select_related("site").all():
            if vlan.site:
                site_slug = vlan.site.slug
            else:
                site_slug = "global"
            if site_slug not in self.vlan_map:
                self.vlan_map[site_slug] = {}
            if str(vlan.vid) not in self.vlan_map[site_slug]:
                self.vlan_map[site_slug][vlan.vid] = {}
            self.vlan_map[site_slug][vlan.vid] = vlan.id
            if self.job.kwargs.get("debug"):
                self.job.log_debug(message=f"Loading VLAN: {vlan.name}.")
            try:
                _vlan = self.vlan(
                    name=vlan.name,
                    vlan_id=vlan.vid,
                    description=vlan.description if vlan.description else "",
                    building=vlan.site.slug if vlan.site else "Unknown",
                    custom_fields=nautobot.get_custom_field_dict(vlan.get_custom_fields()),
                    tags=nautobot.get_tag_strings(vlan.tags),
                    uuid=vlan.id,
                )
                self.add(_vlan)
            except ObjectAlreadyExists as err:
                if self.job.kwargs.get("debug"):
                    self.job.log_warning(message=err)

    def load_cables(self):
        """Add Nautobot Cable objects as DiffSync Connection models."""
        for _cable in Cable.objects.all():
            if _cable.termination_a.device.name not in self.cable_map:
                self.cable_map[_cable.termination_a.device.name] = {}
            if _cable.termination_a.name not in self.cable_map[_cable.termination_a.device.name]:
                self.cable_map[_cable.termination_a.device.name][_cable.termination_a.name] = {}
            self.cable_map[_cable.termination_a.device.name][_cable.termination_a.name] = _cable.id
            if _cable.termination_b.device.name not in self.cable_map:
                self.cable_map[_cable.termination_b.device.name] = {}
            if _cable.termination_b.name not in self.cable_map[_cable.termination_b.device.name]:
                self.cable_map[_cable.termination_b.device.name][_cable.termination_b.name] = {}
            self.cable_map[_cable.termination_b.device.name][_cable.termination_b.name] = _cable.id
            new_conn = self.conn(
                src_device="",
                src_port="",
                src_type="interface",
                dst_device="",
                dst_port="",
                dst_type="interface",
                tags=nautobot.get_tag_strings(_cable.tags),
                uuid=_cable.id,
                src_port_mac=None,
                dst_port_mac=None,
            )
            new_conn = self.add_src_connection(
                cable_term_type=_cable.termination_a_type, cable_term_id=_cable.termination_a_id, connection=new_conn
            )
            new_conn = self.add_dst_connection(
                cable_term_type=_cable.termination_b_type, cable_term_id=_cable.termination_b_id, connection=new_conn
            )
            self.add(new_conn)
            # # Now to ensure that diff matches, add a connection from reverse side.
            # new_conn = self.add_src_connection(
            #     cable_term_type=_cable.termination_b_type, cable_term_id=_cable.termination_b_id, connection=new_conn
            # )
            # new_conn = self.add_dst_connection(
            #     cable_term_type=_cable.termination_a_type, cable_term_id=_cable.termination_a_id, connection=new_conn
            # )
            # self.add(new_conn)

    def add_src_connection(
        self, cable_term_type: Cable, cable_term_id: Cable, connection: dcim.Connection
    ) -> dcim.Connection:
        """Method to fill in source portion of a Connection object.

        Works in conjunction with the `load_cables` and `add_dst_connection` methods.

        Args:
            cable_term_type (Cable): The `termination_a_type` or `termination_b_type` attribute from a Cable object.
            cable_term_id (Cable): The `termination_a_id` or `termination_b_id` attribute from a Cable object.
            connection (dcim.Connection): Connection object being created. Expected to be empty with tags and types default `interface` type set for src side.

        Returns:
            dcim.Connection: Updated Connection object with source attributes populated.
        """
        if "interface" in str(cable_term_type):
            src_port = Interface.objects.get(id=cable_term_id)
            if src_port.mac_address:
                mac_addr = str(src_port.mac_address).replace(":", "").lower()
            else:
                mac_addr = None
            connection.src_port = src_port.name
            connection.src_device = src_port.device.name
            connection.src_port_mac = mac_addr
        elif "circuit" in str(cable_term_type):
            connection.src_type = "circuit"
            connection.src_port = CircuitTermination.objects.get(id=cable_term_id).circuit.cid
            connection.src_device = CircuitTermination.objects.get(id=cable_term_id).circuit.cid
        return connection

    def add_dst_connection(
        self, cable_term_type: Cable, cable_term_id: Cable, connection: dcim.Connection
    ) -> dcim.Connection:
        """Method to fill in destination portion of a Connection object.

        Works in conjunction with the `load_cables` and `add_src_connection` methods.

        Args:
            cable_term_type (Cable): The `termination_a_type` or `termination_b_type` attribute from a Cable object.
            cable_term_id (Cable): The `termination_a_id` or `termination_b_id` attribute from a Cable object.
            connection (dcim.Connection): Connection object being created. Expected to be empty with tags and types default `interface` type set for dst side.

        Returns:
            dcim.Connection: Updated Connection object with destination attributes populated.
        """
        if "interface" in str(cable_term_type):
            dst_port = Interface.objects.get(id=cable_term_id)
            if dst_port.mac_address:
                mac_addr = str(dst_port.mac_address).replace(":", "").lower()
            else:
                mac_addr = None
            connection.dst_port = dst_port.name
            connection.dst_device = dst_port.device.name
            connection.dst_port_mac = mac_addr
        elif "circuit" in str(cable_term_type):
            connection.dst_type = "circuit"
            connection.dst_port = CircuitTermination.objects.get(id=cable_term_id).circuit.cid
            connection.dst_device = CircuitTermination.objects.get(id=cable_term_id).circuit.cid
        return connection

    def load_providers(self):
        """Add Nautobot Provider objects as DiffSync Provider models."""
        for _prov in Provider.objects.all():
            self.provider_map[_prov.name] = _prov.id
            new_prov = self.provider(
                name=_prov.name,
                notes=_prov.comments,
                vendor_url=_prov.portal_url,
                vendor_acct=_prov.account,
                vendor_contact1=_prov.noc_contact,
                vendor_contact2=_prov.admin_contact,
                tags=nautobot.get_tag_strings(_prov.tags),
                uuid=_prov.id,
            )
            self.add(new_prov)

    def load_circuits(self):
        """Add Nautobot Circuit objects as DiffSync Circuit models."""
        for _circuit in Circuit.objects.select_related("provider", "type", "status").all():
            self.circuit_map[_circuit.cid] = _circuit.id
            new_circuit = self.circuit(
                circuit_id=_circuit.cid,
                provider=_circuit.provider.name,
                notes=_circuit.comments,
                type=_circuit.type.name,
                status=_circuit.status.name,
                install_date=_circuit.install_date,
                bandwidth=_circuit.commit_rate,
                tags=nautobot.get_tag_strings(_circuit.tags),
                uuid=_circuit.id,
                origin_int=None,
                origin_dev=None,
                endpoint_int=None,
                endpoint_dev=None,
            )
            if hasattr(_circuit.termination_a, "connected_endpoint") and hasattr(
                _circuit.termination_a.connected_endpoint, "name"
            ):
                new_circuit.origin_int = _circuit.termination_a.connected_endpoint.name
                new_circuit.origin_dev = _circuit.termination_a.connected_endpoint.device.name
            if hasattr(_circuit.termination_z, "connected_endpoint") and hasattr(
                _circuit.termination_z.connected_endpoint, "name"
            ):
                new_circuit.endpoint_int = _circuit.termination_z.connected_endpoint.name
                new_circuit.endpoint_dev = _circuit.termination_z.connected_endpoint.device.name
            self.add(new_circuit)

    def load_front_ports(self):
        """Add Nautobot FrontPort objects as DiffSync PatchPanelFrontPort models."""
        for port in FrontPort.objects.select_related("device").all():
            if port.device.device_role.name == "patch panel":
                if port.device.name not in self.fp_map:
                    self.fp_map[port.device.name] = {}
                self.fp_map[port.device.name][port.name] = port.id
                front_port = self.patchpanelfrontport(
                    name=port.name,
                    patchpanel=port.device.name,
                    port_type=port.type,
                    uuid=port.id,
                )
                self.add(front_port)

    def load_rear_ports(self):
        """Add Nautobot RearPort objects as DiffSync PatchPanelRearPort models."""
        for port in RearPort.objects.select_related("device").all():
            if port.device.device_role.name == "patch panel":
                if port.device.name not in self.rp_map:
                    self.rp_map[port.device.name] = {}
                self.rp_map[port.device.name][port.name] = port.id
                rear_port = self.patchpanelrearport(
                    name=port.name,
                    patchpanel=port.device.name,
                    port_type=port.type,
                    uuid=port.id,
                )
                self.add(rear_port)

    def load(self):
        """Load data from Nautobot."""
        self.status_map = {s.slug: s.id for s in Status.objects.only("id", "slug")}
        self.platform_map = {p.slug: p.id for p in Platform.objects.only("id", "slug")}
        self.devicerole_map = {dr.slug: dr.id for dr in DeviceRole.objects.only("id", "slug")}
        self.relationship_map = {r.name: r.id for r in Relationship.objects.only("id", "name")}
        if LIFECYCLE_MGMT:
            self.softwarelcm_map = nautobot.get_dlc_version_map()
        else:
            self.softwarelcm_map = nautobot.get_cf_version_map()

        # Import all Nautobot Site records as Buildings
        self.load_sites()
        self.load_rackgroups()
        self.load_racks()
        self.load_manufacturers()
        self.load_device_types()
        self.load_vrfs()
        self.load_vlans()
        self.load_prefixes()
        self.load_virtual_chassis()
        self.load_devices()
        self.load_interfaces()
        self.load_ip_addresses()
        self.load_providers()
        self.load_circuits()
        self.load_front_ports()
        self.load_rear_ports()
        # self.load_cables()
