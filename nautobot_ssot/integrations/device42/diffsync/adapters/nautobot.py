"""DiffSync adapter class for Nautobot as source-of-truth."""

from collections import defaultdict
import logging
from diffsync import DiffSync
from diffsync.exceptions import ObjectAlreadyExists, ObjectNotFound
from django.db.models import ProtectedError
from nautobot.circuits.models import Circuit, CircuitTermination, Provider
from nautobot.dcim.models import (
    Cable,
    Device,
    DeviceType,
    FrontPort,
    Interface,
    Location,
    LocationType,
    Manufacturer,
    Platform,
    Rack,
    RackGroup,
    RearPort,
    VirtualChassis,
)
from nautobot.extras.models import Relationship, Role, Status
from nautobot.ipam.models import VLAN, VRF, IPAddress, IPAddressToInterface, Prefix, Namespace
from netutils.lib_mapper import ANSIBLE_LIB_MAPPER

from nautobot_ssot.integrations.device42.constant import PLUGIN_CFG
from nautobot_ssot.integrations.device42.diffsync.models.nautobot import assets, circuits, dcim, ipam
from nautobot_ssot.integrations.device42.utils import nautobot

logger = logging.getLogger(__name__)

try:
    from nautobot_device_lifecycle_mgmt.models import SoftwareLCM  # noqa: F401 # pylint: disable=unused-import

    LIFECYCLE_MGMT = True
except ImportError:
    logger.info("Device Lifecycle app isn't installed so will revert to CustomField for OS version.")
    LIFECYCLE_MGMT = False
except RuntimeError:
    logger.warning(
        "nautobot-device-lifecycle-mgmt is installed but not enabled. Did you forget to add it to your settings.PLUGINS?"
    )
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
    role_map = {}
    devicetype_map = {}
    cluster_map = {}
    device_map = {}
    port_map = {}
    vrf_map = {}
    namespace_map = {}
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

    def __init__(self, *args, job, sync=None, **kwargs):
        """Initialize the Nautobot DiffSync adapter.

        Args:
            job (Device42DataSource): Nautobot Job.
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
        if PLUGIN_CFG.get("device42_delete_on_sync"):
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
                        if self.job.debug:
                            self.job.logger.info(f"Deleting {nautobot_object}.")
                        nautobot_object.delete()
                    except ProtectedError:
                        self.job.logger.warning(f"Deletion failed protected object: {nautobot_object}")
                self.objects_to_delete[grouping] = []
        return super().sync_complete(source, *args, **kwargs)

    def load_sites(self):
        """Add Nautobot Site objects as DiffSync Building models."""
        for site in Location.objects.filter(location_type=LocationType.objects.get_or_create(name="Site")[0]):
            self.site_map[site.name] = site.id
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
            except AttributeError as err:
                self.job.logger.warning(f"Error loading {site.name} : {err}")
                continue

    def load_rackgroups(self):
        """Add Nautobot RackGroup objects as DiffSync Room models."""
        for _rg in RackGroup.objects.select_related("location").all():
            if _rg.location.name not in self.room_map:
                self.room_map[_rg.location.name] = {}
            if _rg.name not in self.room_map[_rg.location.name]:
                self.room_map[_rg.location.name][_rg.name] = {}
            self.room_map[_rg.location.name][_rg.name] = _rg.id
            room = self.room(
                name=_rg.name,
                building=_rg.location.name,
                notes=_rg.description,
                custom_fields=nautobot.get_custom_field_dict(_rg.get_custom_fields()),
                uuid=_rg.id,
            )
            self.add(room)
            _site = self.get(self.building, _rg.location.name)
            _site.add_child(child=room)

    def load_racks(self):
        """Add Nautobot Rack objects as DiffSync Rack models."""
        for rack in Rack.objects.select_related("location", "rack_group").all():
            if rack.location.name not in self.rack_map:
                self.rack_map[rack.location.name] = {}
            if rack.rack_group.name not in self.rack_map[rack.location.name]:
                self.rack_map[rack.location.name][rack.rack_group.name] = {}
            if rack.name not in self.rack_map[rack.location.name][rack.rack_group.name]:
                self.rack_map[rack.location.name][rack.rack_group.name][rack.name] = {}
            self.rack_map[rack.location.name][rack.rack_group.name][rack.name] = rack.id
            try:
                new_rack = self.rack(
                    name=rack.name,
                    building=rack.location.name,
                    room=rack.rack_group.name,
                    height=rack.u_height,
                    numbering_start_from_bottom="no" if rack.desc_units else "yes",
                    tags=nautobot.get_tag_strings(rack.tags),
                    custom_fields=nautobot.get_custom_field_dict(rack.get_custom_fields()),
                    uuid=rack.id,
                )
                self.add(new_rack)
                _room = self.get(self.room, {"name": rack.rack_group, "building": rack.location.name})
                _room.add_child(child=new_rack)
            except ObjectAlreadyExists as err:
                if self.job.debug:
                    self.job.logger.warning(err)

    def load_manufacturers(self):
        """Add Nautobot Manufacturer objects as DiffSync Vendor models."""
        for manu in Manufacturer.objects.all():
            self.vendor_map[manu.name] = manu.id
            new_manu = self.vendor(
                name=manu.name,
                custom_fields=nautobot.get_custom_field_dict(manu.get_custom_fields()),
                uuid=manu.id,
            )
            self.add(new_manu)

    def load_device_types(self):
        """Add Nautobot DeviceType objects as DiffSync Hardware models."""
        for _dt in DeviceType.objects.select_related("manufacturer").all():
            self.devicetype_map[_dt.model] = _dt.id
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
            "status", "device_type", "role", "location", "rack", "platform", "vc_master_for", "virtual_chassis"
        ).all():
            self.device_map[dev.name] = dev.id
            # As patch panels are added as Devices, we need to filter them out for their own load method.
            if dev.role.name == "patch panel":
                patch_panel = self.patchpanel(
                    name=dev.name,
                    in_service=bool(str(dev.status.name) == "Active"),
                    vendor=dev.device_type.manufacturer.name,
                    model=dev.device_type.model,
                    position=dev.position,
                    orientation=dev.face if dev.face else "rear",
                    num_ports=len(FrontPort.objects.filter(device__name=dev.name)),
                    building=dev.location.name,
                    room=dev.rack.rack_group.name if dev.rack else None,
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
                building=dev.location.name,
                room=dev.rack.rack_group.name if dev.rack else "",
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
                if self.job.debug:
                    self.job.logger.debug(f"Loading Interface: {port.name} for {port.device}.")
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
                    status=port.status.name if hasattr(port, "status") else "Active",
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
            if self.job.debug:
                self.job.logger.debug(f"Loading VRF: {vrf.name}.")
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
        for _pf in Prefix.objects.all():
            if _pf.vrfs.first():
                vrf_name = _pf.vrfs.first().name
            else:
                vrf_name = "Unknown"
            if vrf_name not in self.prefix_map:
                self.prefix_map[vrf_name] = {}
            self.prefix_map[vrf_name][str(_pf.prefix)] = _pf.id
            ip_net = _pf.prefix
            if self.job.debug:
                self.job.logger.debug(f"Loading Prefix: {ip_net}.")
            new_pf = self.subnet(
                network=str(ip_net.network),
                mask_bits=ip_net.prefixlen,
                description=_pf.description,
                vrf=vrf_name,
                tags=nautobot.get_tag_strings(_pf.tags),
                custom_fields=nautobot.get_custom_field_dict(_pf.get_custom_fields()),
                uuid=_pf.id,
            )
            self.add(new_pf)

    def load_ip_addresses(self):
        """Add Nautobot IPAddress objects as DiffSync IPAddress models."""
        for _ip in IPAddress.objects.select_related("status", "parent").all():
            parent_prefix = str(_ip.parent.prefix)
            if parent_prefix not in self.ipaddr_map:
                self.ipaddr_map[parent_prefix] = {}
            if str(_ip.address) not in self.ipaddr_map[parent_prefix]:
                self.ipaddr_map[parent_prefix][str(_ip.address)] = {}
            self.ipaddr_map[parent_prefix][str(_ip.address)] = _ip.id
            if self.job.debug:
                self.job.logger.debug(f"Loading IPAddress: {_ip.address}.")
            new_ip = self.ipaddr(
                address=str(_ip.address),
                subnet=parent_prefix,
                namespace=_ip.parent.namespace.name,
                available=bool(_ip.status.name != "Active"),
                label=_ip.description,
                tags=nautobot.get_tag_strings(_ip.tags),
                interface="",
                device="",
                custom_fields=nautobot.get_custom_field_dict(_ip.get_custom_fields()),
                uuid=_ip.id,
                primary=None,
            )
            for pair in IPAddressToInterface.objects.filter(ip_address=_ip):
                if getattr(pair, "interface"):
                    new_ip.interface = pair[0].interface.name
                    new_ip.device = pair[0].interface.device.name
                elif getattr(pair, "vm_interface"):
                    new_ip.interface = pair[0].vm_interface.name
                    new_ip.device = pair[0].vm_interface.device.name
            if hasattr(_ip, "primary_ip4_for") or hasattr(_ip, "primary_ip6_for"):
                new_ip.primary = True
            else:
                new_ip.primary = False
            try:
                self.add(new_ip)
            except ObjectAlreadyExists as err:
                if self.job.debug:
                    self.job.logger.debug(
                        f"Duplicate IP Address {_ip.address} found and won't be imported. Validate the duplicate address is accurate. {err}"
                    )

    def load_vlans(self):
        """Add Nautobot VLAN objects as DiffSync VLAN models."""
        for vlan in VLAN.objects.select_related("location").all():
            if vlan.location:
                site_name = vlan.location.name
            else:
                site_name = "Global"
            if site_name not in self.vlan_map:
                self.vlan_map[site_name] = {}
            if str(vlan.vid) not in self.vlan_map[site_name]:
                self.vlan_map[site_name][vlan.vid] = {}
            self.vlan_map[site_name][vlan.vid] = vlan.id
            if self.job.debug:
                self.job.logger.debug(f"Loading VLAN: {vlan.name}.")
            try:
                _vlan = self.vlan(
                    name=vlan.name,
                    vlan_id=vlan.vid,
                    description=vlan.description if vlan.description else "",
                    building=vlan.location.name if vlan.location else "Unknown",
                    custom_fields=nautobot.get_custom_field_dict(vlan.get_custom_fields()),
                    tags=nautobot.get_tag_strings(vlan.tags),
                    uuid=vlan.id,
                )
                self.add(_vlan)
            except ObjectAlreadyExists as err:
                if self.job.debug:
                    self.job.logger.warning(err)

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
        for _circuit in Circuit.objects.select_related("provider", "circuit_type", "status").all():
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
            if port.device.role.name == "patch panel":
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
            if port.device.role.name == "patch panel":
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
        self.status_map = {s.name: s.id for s in Status.objects.only("id", "name")}
        self.platform_map = {p.name: p.id for p in Platform.objects.only("id", "name")}
        self.role_map = {dr.name: dr.id for dr in Role.objects.only("id", "name")}
        self.namespace_map = {ns.name: ns.id for ns in Namespace.objects.only("id", "name")}
        self.relationship_map = {r.label: r.id for r in Relationship.objects.only("id", "label")}
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
