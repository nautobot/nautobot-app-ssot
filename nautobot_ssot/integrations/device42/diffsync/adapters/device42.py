"""DiffSync adapter for Device42."""

import re
from decimal import Decimal
from typing import List
import ipaddress
from diffsync import DiffSync
from diffsync.exceptions import ObjectAlreadyExists, ObjectNotFound
from nautobot.core.settings_funcs import is_truthy
from netutils.bandwidth import name_to_bits
from netutils.dns import fqdn_to_ip, is_fqdn_resolvable
from nautobot_ssot.integrations.device42.constant import PLUGIN_CFG
from nautobot_ssot.integrations.device42.diffsync.models.base import assets, circuits, dcim, ipam
from nautobot_ssot.integrations.device42.utils.device42 import (
    get_facility,
    get_intf_type,
    get_intf_status,
    get_netmiko_platform,
    get_custom_field_dict,
    load_vlan,
)
from nautobot_ssot.integrations.device42.utils.nautobot import determine_vc_position


def sanitize_string(san_str: str):
    """Sanitize string to ensure it doesn't have invisible characters."""
    return san_str.replace("\u200b", "").replace("\r", "").rstrip("-")


def get_circuit_status(status: str) -> str:
    """Map Device42 Status to Nautobot Status.

    Args:
        status (str): Device42 Status to be mapped.

    Returns:
        str: Device42 mapped Status.
    """
    STATUS_MAP = {
        "Production": "Active",
        "Provisioning": "Provisioning",
        "Canceled": "Deprovisioning",
        "Decommissioned": "Decommissioned",
    }
    if status in STATUS_MAP:
        return STATUS_MAP[status]
    else:
        return "Offline"


def get_site_from_mapping(device_name: str) -> str:
    """Method to map a Device to a Site based upon their name using a regex pattern in the settings.

    This works in conjunction with the `hostname_mapping` setting to have a Device assigned to a Site by hostname. This is done using a regex pattern mapped to the Site slug.

    Args:
        device_name (str): Name of the Device to be matched. Must match one of the regex patterns provided to get a response.

    Returns:
        str: The Site slug of the associated Site for the Device in the mapping. Returns blank string if match not found.
    """
    for _entry in PLUGIN_CFG["device42_hostname_mapping"]:
        for _mapping, _name in _entry.items():
            site_match = re.match(_mapping, device_name)
            if site_match:
                return _name
    return ""


def get_dns_a_record(dev_name: str):
    """Method to obtain A record for a Device.

    Args:
        dev_name (str): Name of Device to perform DNS query for.

    Returns:
        str: A record for Device if exists, else False.
    """
    if is_fqdn_resolvable(dev_name):
        return fqdn_to_ip(dev_name)
    else:
        return False


class Device42Adapter(DiffSync):
    """DiffSync adapter using requests to communicate to Device42 server."""

    building = dcim.Building
    room = dcim.Room
    rack = dcim.Rack
    vendor = dcim.Vendor
    hardware = dcim.Hardware
    cluster = dcim.Cluster
    device = dcim.Device
    port = dcim.Port
    vrf = ipam.VRFGroup
    subnet = ipam.Subnet
    ipaddr = ipam.IPAddress
    vlan = ipam.VLAN
    conn = dcim.Connection
    provider = circuits.Provider
    circuit = circuits.Circuit
    patchpanel = assets.PatchPanel
    patchpanelfrontport = assets.PatchPanelFrontPort
    patchpanelrearport = assets.PatchPanelRearPort

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

    def __init__(self, *args, job, sync=None, client, **kwargs):
        """Initialize Device42Adapter.

        Args:
            job (Device42DataSource): Nautobot Job.
            sync (object, optional): Nautobot DiffSync. Defaults to None.
            client (object): Device42API client connection object.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.device42_hardware_dict = {}
        self.device42 = client
        self.device42_clusters = self.device42.get_cluster_members()
        self.rack_elevations = {}

        # mapping of SiteCode (facility) to Building name
        self.d42_building_sitecode_map = {}
        # mapping of Building PK to Building info
        self.d42_building_map = self.device42.get_building_pks()
        # mapping of Customer PK to Customer info
        self.d42_customer_map = self.device42.get_customer_pks()
        # mapping of Room PK to Room info
        self.d42_room_map = self.device42.get_room_pks()
        # mapping of Rack PK to Rack info
        self.d42_rack_map = self.device42.get_rack_pks()
        # mapping of VLAN PK to VLAN name and ID
        self.d42_vlan_map = self.device42.get_vlan_info()
        # mapping of Device PK to Device name
        self.d42_device_map = self.device42.get_device_pks()
        # mapping of Port PK to Port name
        self.d42_port_map = self.device42.get_port_pks()
        # mapping of Vendor PK to Vendor info
        self.d42_vendor_map = {vendor["name"]: vendor for vendor in self.device42.get_vendors()}
        self.d42_hardware_map = {
            sanitize_string(hwmodel["name"]): hwmodel for hwmodel in self.device42.get_hardware_models()
        }
        # default custom fields for IP Address
        self.d42_ipaddr_default_cfs = self.device42.get_ipaddr_default_custom_fields()
        # mapping of Subnet PK to Subnet info
        self.d42_subnet_map = self.device42.get_subnets()

    def get_building_for_device(self, dev_record: dict) -> str:
        """Method to determine the Building (Site) for a Device.

        Args:
            dev_record (dict): Dictionary of Device information from Device42. Needs to have name, customer, and building keys depending upon enabled app settings.

        Returns:
            str: Slugified version of the Building (Site) for a Device.
        """
        _building = False
        if PLUGIN_CFG.get("device42_hostname_mapping") and len(PLUGIN_CFG["device42_hostname_mapping"]) > 0:
            _building = get_site_from_mapping(device_name=dev_record["name"])

        if not _building:
            if (
                PLUGIN_CFG.get("device42_customer_is_facility")
                and dev_record.get("customer")
                and dev_record["customer"] in self.d42_building_sitecode_map
            ):
                _building = self.d42_building_sitecode_map[dev_record["customer"].upper()]
            else:
                _building = dev_record.get("building")
        if _building is not None:
            return _building
        return ""

    def load_buildings(self):
        """Load Device42 buildings."""
        for record in self.device42.get_buildings():
            self.job.logger.info(f"Loading {record['name']} building from Device42.")
            _tags = record["tags"] if record.get("tags") else []
            if len(_tags) > 1:
                _tags.sort()
            building = self.building(
                name=record["name"],
                address=sanitize_string(record["address"]) if record.get("address") else "",
                latitude=float(round(Decimal(record["latitude"] if record["latitude"] else 0.0), 6)),
                longitude=float(round(Decimal(record["longitude"] if record["longitude"] else 0.0), 6)),
                contact_name=record["contact_name"] if record.get("contact_name") else "",
                contact_phone=record["contact_phone"] if record.get("contact_phone") else "",
                rooms=record["rooms"] if record.get("rooms") else [],
                custom_fields=get_custom_field_dict(record["custom_fields"]),
                tags=_tags,
                uuid=None,
            )
            _facility = get_facility(tags=_tags)
            if _facility:
                self.d42_building_sitecode_map[_facility.upper()] = record["name"]
            try:
                self.add(building)
            except ObjectAlreadyExists as err:
                if self.job.debug:
                    self.job.logger.warning(f"{record['name']} is already loaded. {err}")

    def load_rooms(self):
        """Load Device42 rooms."""
        for record in self.device42.get_rooms():
            self.job.logger.info(f"Loading {record['name']} room from Device42.")
            _tags = record["tags"] if record.get("tags") else []
            if len(_tags) > 1:
                _tags.sort()
            if record.get("building"):
                if record["building"] not in self.rack_elevations:
                    self.rack_elevations[record["building"]] = {}
                if record["name"] not in self.rack_elevations[record["building"]]:
                    self.rack_elevations[record["building"]][record["name"]] = {}
                room = self.room(
                    name=record["name"],
                    building=record["building"],
                    notes=record["notes"] if record.get("notes") else "",
                    custom_fields=get_custom_field_dict(record["custom_fields"]),
                    tags=_tags,
                    uuid=None,
                )
                try:
                    self.add(room)
                    _site = self.get(self.building, record.get("building"))
                    _site.add_child(child=room)
                except ObjectAlreadyExists as err:
                    if self.job.debug:
                        self.job.logger.warning(f"{record['name']} is already loaded. {err}")
            else:
                self.job.logger.warning(f"{record['name']} is missing Building and won't be imported.")
                continue

    def load_racks(self):
        """Load Device42 racks."""
        self.job.logger.info("Loading racks from Device42.")
        for record in self.device42.get_racks():
            _tags = record["tags"] if record.get("tags") else []
            if len(_tags) > 1:
                _tags.sort()
            if record.get("building") and record.get("room"):
                self.rack_elevations[record["building"]][record["room"]][record["name"]] = {
                    slot: [] for slot in range(1, record["size"] + 1)
                }
                rack = self.rack(
                    name=record["name"],
                    building=record["building"],
                    room=record["room"],
                    height=record["size"] if record.get("size") else 1,
                    numbering_start_from_bottom=record["numbering_start_from_bottom"],
                    custom_fields=get_custom_field_dict(record["custom_fields"]),
                    tags=_tags,
                    uuid=None,
                )
                try:
                    self.add(rack)
                    _room = self.get(
                        self.room, {"name": record["room"], "building": record["building"], "room": record["room"]}
                    )
                    _room.add_child(child=rack)
                except ObjectAlreadyExists as err:
                    if self.job.debug:
                        self.job.logger.warning(f"Rack {record['name']} already exists. {err}")
            else:
                self.job.logger.warning(f"{record['name']} is missing Building and Room and won't be imported.")
                continue

    def get_cluster_host(self, device: str) -> str:
        """Get name of cluster host if device is in a cluster.

        Args:
            device (str): Name of device to see if part of cluster.

        Returns:
            str: Name of cluster device is part of or empty string.
        """
        for _cluster, _info in self.device42_clusters.items():
            if device in _info["members"]:
                return _cluster
        return ""

    def load_cluster(self, cluster_info: dict):
        """Load Device42 clusters into DiffSync model.

        Args:
            cluster_info (dict): Information of cluster to be added to DiffSync model.

        Returns:
            models.Cluster: Cluster model that has been created or found.
        """
        try:
            _cluster = self.get(self.cluster, cluster_info["name"][:64])
        except ObjectAlreadyExists as err:
            if self.job.debug:
                self.job.logger.warning(f"Cluster {cluster_info['name']} already has been added. {err}")
        except ObjectNotFound:
            self.job.logger.info(f"Cluster {cluster_info['name']} being loaded from Device42.")
            _clus = self.device42_clusters[cluster_info["name"]]
            _tags = cluster_info["tags"] if cluster_info.get("tags") else []
            if PLUGIN_CFG.get("device42_ignore_tag") and PLUGIN_CFG["device42_ignore_tag"] in _tags:
                self.job.logger.warning(f"Cluster {cluster_info['name']} has ignore tag so skipping.")
                return
            if len(_tags) > 1:
                _tags.sort()
            _cluster = self.cluster(
                name=cluster_info["name"][:64],
                members=_clus["members"],
                tags=_tags,
                custom_fields=get_custom_field_dict(cluster_info["custom_fields"]),
                uuid=None,
            )
            self.add(_cluster)
            # Add master device to hold stack info like intfs and IPs
            _building = self.get_building_for_device(dev_record={**_clus, **cluster_info})
            _device = self.device(
                name=cluster_info["name"][:64],
                building=_building if _building else "",
                rack="",
                rack_orientation="rear",
                room="",
                hardware=sanitize_string(_clus["hardware"]),
                os=get_netmiko_platform(_clus["os"][:100]) if _clus.get("os") else "",
                in_service=cluster_info.get("in_service"),
                tags=_tags,
                cluster_host=cluster_info["name"][:64],
                master_device=True,
                serial_no="",
                custom_fields=get_custom_field_dict(cluster_info["custom_fields"]),
                rack_position=None,
                os_version="",
                vc_position=1,
                uuid=None,
            )
            self.add(_device)

    def load_devices_and_clusters(self):
        """Load Device42 devices."""
        self.job.logger.info("Retrieving devices from Device42.")
        _devices = self.device42.get_devices()

        # Add all Clusters first
        for _record in _devices:
            if _record.get("type") == "cluster" and _record.get("name") in self.device42_clusters:
                self.load_cluster(_record)

        # Then iterate through again and add Devices
        for _record in _devices:
            rack_position, model = None, None
            self.job.logger.info(f"Device {_record['name']} being loaded.")
            _building = self.get_building_for_device(dev_record=_record)
            # only consider devices that have a Building
            if _building == "":
                self.job.logger.warning(
                    f"Device {_record['name']} can't be loaded as we're unable to find associated Building."
                )
                continue
            if _record.get("type") != "cluster" and _record.get("hw_model"):
                hwmodel_name = sanitize_string(_record["hw_model"])
                manuf = self.d42_hardware_map[hwmodel_name]["manufacturer"]
                self.job.logger.info(f"Loading hardware model {manuf} {hwmodel_name} from Device42.")
                model = self.load_vendor_and_model(hwmodel_name, manuf)
                _tags = _record["tags"] if _record.get("tags") else []
                if PLUGIN_CFG.get("device42_ignore_tag") and PLUGIN_CFG["device42_ignore_tag"] in _tags:
                    self.job.logger.warning(f"Skipping loading {_record['name']} as it has the specified ignore tag.")
                    continue
                if len(_tags) > 1:
                    _tags.sort()
                # Get size of model to ensure appropriate number of rack Us are filled
                if model:
                    model_size = int(model.size)
                    if _record.get("start_at"):
                        rack_position = int(_record["start_at"])
                        for slot in range(rack_position, rack_position + model_size + 1):
                            if _building not in self.rack_elevations:
                                self.rack_elevations[_building] = {}

                            if _record["room"] not in self.rack_elevations[_building]:
                                self.rack_elevations[_building][_record["room"]] = {}

                            if _record["rack"] not in self.rack_elevations[_building][_record["room"]]:
                                self.rack_elevations[_building][_record["room"]][_record["rack"]] = {}

                            if slot not in self.rack_elevations[_building][_record["room"]][_record["rack"]]:
                                self.rack_elevations[_building][_record["room"]][_record["rack"]][slot] = []

                            self.rack_elevations[_building][_record["room"]][_record["rack"]][slot].append(
                                _record["name"][:64]
                            )

                        if (
                            len(
                                self.rack_elevations[_building][_record["room"]][_record["rack"]][
                                    int(_record["start_at"])
                                ]
                            )
                            > 1
                        ):
                            rack_position = None
                _device = self.device(
                    name=_record["name"][:64],
                    building=_building,
                    room=_record["room"] if _record.get("room") else "",
                    rack=_record["rack"] if _record.get("rack") else "",
                    rack_position=rack_position,
                    rack_orientation="front" if _record.get("orientation") == 1 else "rear",
                    hardware=sanitize_string(_record["hw_model"]),
                    os=get_netmiko_platform(_record["os"][:100]) if _record.get("os") else "",
                    os_version=re.sub(r"^[a-zA-Z]+\s", "", _record["osver"]) if _record.get("osver") else "",
                    in_service=_record.get("in_service"),
                    serial_no=_record["serial_no"],
                    master_device=False,
                    tags=_tags,
                    custom_fields=get_custom_field_dict(_record["custom_fields"]),
                    cluster_host=None,
                    vc_position=None,
                    uuid=None,
                )
                self.assign_cluster_host(_record, _device)
                try:
                    self.add(_device)
                except ObjectAlreadyExists as err:
                    self.job.logger.warning(f"Duplicate device attempting to be added. {err}")
                    continue
            elif _record.get("type") != "cluster" and not _record.get("hw_model"):
                self.job.logger.warning(f"Device {_record['name']}'s hardware isn't specified so won't be loaded.")

    def load_vendor_and_model(self, hwmodel_name: str, manuf: str):
        """Load Vendor and Hardware DiffSync models with information from other functions.

        Args:
            hwmodel_name (str): Hardware model name.
            manuf (str): Hardware model manufacturer/vendor.

        Returns:
            dcim.Hardware: DiffSync model for Hardware that was loaded.
        """
        hwmodel_name = sanitize_string(hwmodel_name)
        try:
            self.get(self.vendor, manuf)
        except ObjectNotFound:
            vendor = self.vendor(
                name=manuf,
                custom_fields=get_custom_field_dict(self.d42_vendor_map[manuf]["custom_fields"]),
                uuid=None,
            )
            self.add(vendor)
        try:
            hwmodel = self.get(self.hardware, hwmodel_name)
        except ObjectNotFound:
            hwmodel = self.hardware(
                name=hwmodel_name,
                manufacturer=manuf,
                size=(
                    float(round(self.d42_hardware_map[hwmodel_name]["size"]))
                    if self.d42_hardware_map.get(hwmodel_name) and self.d42_hardware_map[hwmodel_name].get("size")
                    else 1.0
                ),
                depth=(
                    self.d42_hardware_map[hwmodel_name]["depth"]
                    if self.d42_hardware_map.get(hwmodel_name) and self.d42_hardware_map[hwmodel_name].get("depth")
                    else "Half Depth"
                ),
                part_number=(
                    self.d42_hardware_map[hwmodel_name]["part_no"]
                    if self.d42_hardware_map.get(hwmodel_name) and self.d42_hardware_map[hwmodel_name].get("part_no")
                    else ""
                ),
                custom_fields=(
                    get_custom_field_dict(self.d42_hardware_map[hwmodel_name]["custom_fields"])
                    if self.d42_hardware_map.get(hwmodel_name)
                    else {}
                ),
                uuid=None,
            )
            self.add(hwmodel)
        return hwmodel

    def assign_cluster_host(self, _record, _device):
        """Assign cluster host to loaded Device if found.

        Args:
            _record (dict): Device record from Device42 API.
            _device (NautobotDevice): NautobotDevice DiffSync model.
        """
        cluster_host = self.get_cluster_host(_record["name"])
        if cluster_host:
            if not is_truthy(self.device42_clusters[cluster_host]["is_network"]):
                self.job.logger.warning(
                    f"{cluster_host} has network device members but isn't marked as network device. This should be corrected in Device42."
                )
            _device.cluster_host = cluster_host
            if _device.name == cluster_host:
                _device.master_device = True
                _device.vc_position = 1
            else:
                _device.vc_position = determine_vc_position(
                    vc_map=self.device42_clusters, virtual_chassis=cluster_host, device_name=_record["name"]
                )

    def assign_version_to_master_devices(self):
        """Update all Master Devices in Cluster to have OS Version of first device in stack."""
        for cluster in self.get_all(self.cluster):
            try:
                first_in_stack = self.get(self.device, self.device42_clusters[cluster.name]["members"][0])
                try:
                    master_device = self.get(self.device, cluster.name)
                    if first_in_stack.os_version != "":
                        self.job.logger.info(f"Assigning {first_in_stack.os_version} version to {master_device.name}.")
                        master_device.os_version = first_in_stack.os_version
                    else:
                        self.job.logger.info(
                            f"Software version for {first_in_stack.name} is blank so will not assign version to {master_device.name}."
                        )
                except ObjectNotFound:
                    self.job.logger.warning(f"Unable to find VC Master Device {cluster.name} to assign version.")
            except KeyError as err:
                self.job.logger.warning(f"Unable to find cluster host in device42_clusters dictionary. {err}")
            except ObjectNotFound as err:
                self.job.logger.warning(
                    f"Unable to find cluster member {self.device42_clusters[cluster.name]['members'][0]}. {err}"
                )

    def load_ports(self):
        """Load Device42 ports."""
        vlan_ports = self.device42.get_ports_with_vlans()
        no_vlan_ports = self.device42.get_ports_wo_vlans()
        merged_ports = self.filter_ports(vlan_ports, no_vlan_ports)
        default_cfs = self.device42.get_port_default_custom_fields()
        _cfs = self.device42.get_port_custom_fields()
        for _port in merged_ports:
            if _port.get("second_device_fk"):
                _device_name = self.d42_device_map[_port["second_device_fk"]]["name"]
            else:
                _device_name = _port["device_name"]
            if _port.get("port_name"):
                _port_name = _port["port_name"][:63].strip()
            else:
                _port_name = _port["hwaddress"]
            try:
                _dev = self.get(self.device, _device_name)
            except ObjectNotFound:
                if self.job.debug:
                    self.job.logger.warning(
                        f"Skipping loading of Port {_port_name} for Device {_device_name} as device was not loaded."
                    )
                continue
            if self.job.debug:
                self.job.logger.info(f"Loading Port {_port_name} for Device {_device_name}")
            _tags = _port["tags"].split(",") if _port.get("tags") else []
            if len(_tags) > 1:
                _tags.sort()
            _status = get_intf_status(port=_port)
            try:
                self.get(self.port, {"device": _device_name, "name": _port_name})
            except ObjectNotFound:
                new_port = self.port(
                    name=_port_name,
                    device=_device_name,
                    enabled=is_truthy(_port["up_admin"]),
                    mtu=_port["mtu"] if _port.get("mtu") in range(1, 65537) else 1500,
                    description=_port["description"],
                    mac_addr=_port["hwaddress"][:13],
                    type=get_intf_type(intf_record=_port),
                    tags=_tags,
                    mode="access",
                    status=_status,
                    vlans=[],
                    custom_fields=default_cfs,
                    uuid=None,
                )
                if _port.get("vlan_pks"):
                    _vlans = []
                    if _dev.building == "":
                        building = "Unknown"
                    else:
                        building = _dev.building
                    for _pk in _port["vlan_pks"]:
                        if _pk in self.d42_vlan_map and self.d42_vlan_map[_pk]["vid"] != 0:
                            # Need to ensure that there's a VLAN loaded for every one that's being tagged.
                            try:
                                self.get(self.vlan, {"vlan_id": self.d42_vlan_map[_pk]["vid"], "building": building})
                            except ObjectNotFound:
                                load_vlan(
                                    diffsync=self,
                                    vlan_id=self.d42_vlan_map[_pk]["vid"],
                                    site_name=building,
                                )
                            _vlans.append(self.d42_vlan_map[_pk]["vid"])
                    new_port.vlans = sorted(set(_vlans))
                    if len(_vlans) > 1:
                        new_port.mode = "tagged"
                if _device_name in _cfs and _cfs[_device_name].get(_port_name):
                    new_port.custom_fields = _cfs[_device_name][_port_name]
                self.add(new_port)
                _dev.add_child(new_port)

    @staticmethod
    def filter_ports(vlan_ports: List[dict], no_vlan_ports: List[dict]) -> List[dict]:
        """Method to combine lists of ports while removing duplicates.

        Args:
            vlan_ports (List[dict]): List of Ports with tagged VLANs.
            no_vlan_ports (List[dict]): List of Ports without VLANs.

        Returns:
            List[dict]: Merged list of Ports with duplicates removed.
        """
        no_vlan_ports_only = []
        for no_vlan_port in no_vlan_ports:
            for vlan_port in vlan_ports:
                if no_vlan_port["netport_pk"] == vlan_port["netport_pk"]:
                    break
            else:
                no_vlan_ports_only.append(no_vlan_port)
        return vlan_ports + no_vlan_ports_only

    def load_vrfgroups(self):
        """Load Device42 VRFGroups."""
        for _grp in self.device42.get_vrfgroups():
            self.job.logger.info(f"Loading VRF group {_grp['name']} from Device42.")
            try:
                _tags = _grp["tags"] if _grp.get("tags") else []
                if len(_tags) > 1:
                    _tags.sort()
                new_vrf = self.vrf(
                    name=_grp["name"],
                    description=_grp["description"],
                    tags=_tags,
                    custom_fields=get_custom_field_dict(_grp["custom_fields"]),
                    uuid=None,
                )
                self.add(new_vrf)
            except ObjectAlreadyExists as err:
                if self.job.debug:
                    self.job.logger.warning(f"VRF Group {_grp['name']} already exists. {err}")
                continue

    def load_subnets(self):
        """Load Device42 Subnets."""
        self.job.logger.info("Loading Subnets from Device42.")
        default_cfs = self.device42.get_subnet_default_custom_fields()
        _cfs = self.device42.get_subnet_custom_fields()
        for _pf in self.d42_subnet_map:
            _tags = _pf["tags"].split(",") if _pf.get("tags") else []
            if len(_tags) > 1:
                _tags.sort()
            try:
                new_pf = self.subnet(
                    network=_pf["network"],
                    mask_bits=_pf["mask_bits"],
                    description=_pf["name"],
                    vrf=_pf["vrf"],
                    tags=_tags,
                    custom_fields=default_cfs,
                    uuid=None,
                )
                if _cfs.get(f"{_pf['network']}/{_pf['mask_bits']}"):
                    new_pf.custom_fields = _cfs[f"{_pf['network']}/{_pf['mask_bits']}"]
                self.add(new_pf)
            except ObjectAlreadyExists as err:
                if self.job.debug:
                    self.job.logger.warning(f"Subnet {_pf['network']} {_pf['mask_bits']} {_pf['vrf']} {err}")
                continue

    def load_ip_addresses(self):
        """Load Device42 IP Addresses."""
        self.job.logger.info("Loading IP Addresses from Device42.")
        _cfs = self.device42.get_ipaddr_custom_fields()
        for _ip in self.device42.get_ip_addrs():
            _ipaddr = f"{_ip['ip_address']}/{str(_ip['netmask'])}"
            try:
                _device_name, _port_name = "", ""
                if _ip.get("netport_pk") and _ip["netport_pk"] in self.d42_port_map:
                    port_pk = _ip["netport_pk"]
                    if self.d42_port_map[port_pk].get("second_device_fk"):
                        secondary_device_fk = self.d42_port_map[port_pk]["second_device_fk"]
                        _device_name = self.d42_device_map[secondary_device_fk]["name"]
                        self.job.logger.info(
                            f"Primary: {self.d42_port_map[port_pk]['device']}/Secondary: {_device_name} found for {_ipaddr}."
                        )
                    else:
                        _device_name = self.d42_port_map[port_pk]["device"]
                    if self.d42_port_map[port_pk].get("port"):
                        _port_name = self.d42_port_map[port_pk]["port"]
                    else:
                        _port_name = self.d42_port_map[port_pk]["hwaddress"]
                    try:
                        self.get(self.device, _device_name)
                    except ObjectNotFound:
                        # if the Device isn't being imported there's no reason to have the Device name and interface for it to try and match
                        _device_name, _port_name = "", ""
                _tags = sorted(_ip["tags"].split(",")) if _ip.get("tags") != "" else []
                new_ip = self.ipaddr(
                    address=_ipaddr,
                    subnet=f"{_ip['subnet']}/{str(_ip['netmask'])}",
                    namespace=_ip["vrf"] if _ip.get("vrf") else "Global",
                    available=_ip["available"],
                    label=_ip["label"] if _ip.get("label") else "",
                    device=_device_name,
                    interface=_port_name,
                    primary=False,
                    tags=_tags,
                    custom_fields=self.d42_ipaddr_default_cfs,
                    uuid=None,
                )
                if _cfs.get(_ipaddr):
                    new_ip.custom_fields = _cfs[_ipaddr]
                self.add(new_ip)
            except ObjectAlreadyExists as err:
                if self.job.debug:
                    self.job.logger.warning(f"IP Address {_ipaddr} already exists.{err}")
                continue

    def load_vlans(self):
        """Load Device42 VLANs."""
        _vlans = self.device42.get_vlans_with_location()
        for _info in _vlans:
            _vlan_name = _info["vlan_name"].strip()
            building = None
            if _info["vlan_pk"] in self.d42_vlan_map and self.d42_vlan_map[_info["vlan_pk"]].get("custom_fields"):
                _cfs = get_custom_field_dict(self.d42_vlan_map[_info["vlan_pk"]]["custom_fields"])
            else:
                _cfs = {}
            tags = _info["tags"].split(",").sort() if _info.get("tags") else []
            if (
                PLUGIN_CFG.get("device42_customer_is_facility")
                and is_truthy(PLUGIN_CFG.get("device42_customer_is_facility"))
                and _info.get("customer")
            ):
                building = self.d42_building_sitecode_map[_info["customer"].upper()]
            elif _info.get("building"):
                building = _info["building"]
            load_vlan(
                diffsync=self,
                vlan_id=int(_info["vid"]),
                site_name=building if building else "Unknown",
                vlan_name=_vlan_name,
                description=_info["description"] if _info.get("description") else "",
                custom_fields=_cfs,
                tags=tags,
            )

    def load_connections(self):
        """Load Device42 connections."""
        _port_conns = self.device42.get_port_connections()
        devices = self.dict()["device"]
        for _conn in _port_conns:
            if _conn.get("second_src_device"):
                if self.d42_device_map[_conn["second_src_device"]]["name"] not in devices:
                    continue
            if self.d42_device_map[_conn["src_device"]]["name"] not in devices:
                continue
            try:
                new_conn = self.conn(
                    src_device=(
                        self.d42_device_map[_conn["second_src_device"]]["name"]
                        if _conn.get("second_src_device")
                        else self.d42_device_map[_conn["src_device"]]["name"]
                    ),
                    src_port=self.d42_port_map[_conn["src_port"]]["port"],
                    src_port_mac=self.d42_port_map[_conn["src_port"]]["hwaddress"],
                    src_type="interface",
                    dst_device=self.d42_port_map[_conn["dst_port"]]["device"],
                    dst_port=self.d42_port_map[_conn["dst_port"]]["port"],
                    dst_port_mac=self.d42_port_map[_conn["dst_port"]]["hwaddress"],
                    dst_type="interface",
                    tags=None,
                    uuid=None,
                )
                self.add(new_conn)
            except ObjectAlreadyExists as err:
                if self.job.debug:
                    self.job.logger.warning(err)
                continue

    def load_provider(self, provider_info: dict):
        """Load Device42 Providers."""
        _prov = self.d42_vendor_map[provider_info["name"]]
        try:
            self.get(self.provider, _prov.get("name"))
        except ObjectNotFound:
            new_provider = self.provider(
                name=_prov["name"],
                notes=_prov["notes"],
                vendor_url=_prov["home_page"],
                vendor_acct=_prov["account_no"][:30],
                vendor_contact1=_prov["escalation_1"],
                vendor_contact2=_prov["escalation_2"],
                tags=None,
                uuid=None,
            )
            self.add(new_provider)

    def load_providers_and_circuits(self):
        """Load Device42 Providrs and Telco Circuits."""
        _circuits = self.device42.get_telcocircuits()
        origin_int, origin_dev, endpoint_int, endpoint_dev = False, False, False, False
        ppanel_ports = self.device42.get_patch_panel_port_pks()
        for _tc in _circuits:
            self.load_provider(_tc)
            if _tc["origin_type"] == "Device Port" and _tc["origin_netport_fk"] is not None:
                origin_int = self.d42_port_map[_tc["origin_netport_fk"]]["port"]
                origin_dev = self.d42_port_map[_tc["origin_netport_fk"]]["device"]
            if _tc["end_point_type"] == "Device Port" and _tc["end_point_netport_fk"] is not None:
                endpoint_int = self.d42_port_map[_tc["end_point_netport_fk"]]["port"]
                endpoint_dev = self.d42_port_map[_tc["end_point_netport_fk"]]["device"]
            if _tc["origin_type"] == "Patch panel port" and _tc["origin_patchpanelport_fk"] is not None:
                origin_int = ppanel_ports[_tc["origin_patchpanelport_fk"]]["number"]
                origin_dev = ppanel_ports[_tc["origin_patchpanelport_fk"]]["name"]
            if _tc["end_point_type"] == "Patch panel port" and _tc["end_point_patchpanelport_fk"] is not None:
                origin_int = ppanel_ports[_tc["end_point_patchpanelport_fk"]]["number"]
                origin_dev = ppanel_ports[_tc["end_point_patchpanelport_fk"]]["name"]
            new_circuit = self.circuit(
                circuit_id=_tc["circuit_id"],
                provider=self.d42_vendor_map[_tc["vendor_fk"]]["name"],
                notes=_tc["notes"],
                type=_tc["type_name"],
                status=get_circuit_status(_tc["status"]),
                install_date=_tc["turn_on_date"] if _tc.get("turn_on_date") else _tc["provision_date"],
                origin_int=origin_int if origin_int else None,
                origin_dev=origin_dev if origin_dev else None,
                endpoint_int=endpoint_int if endpoint_int else None,
                endpoint_dev=endpoint_dev if endpoint_dev else None,
                bandwidth=name_to_bits(f"{_tc['bandwidth']}{_tc['unit'].capitalize()}") / 1000,
                tags=_tc["tags"].split(",") if _tc.get("tags") else [],
                uuid=None,
            )
            self.add(new_circuit)
            # Add Connection from A side connection Device to Circuit
            if origin_dev and origin_int:
                a_side_conn = self.conn(
                    src_device=origin_dev,
                    src_port=origin_int,
                    src_port_mac=(
                        self.d42_port_map[_tc["origin_netport_fk"]]["hwaddress"]
                        if _tc["origin_type"] == "Device"
                        else None
                    ),
                    src_type="interface" if _tc["origin_type"] == "Device Port" else "patch panel",
                    dst_device=_tc["circuit_id"],
                    dst_port=_tc["circuit_id"],
                    dst_type="circuit",
                    dst_port_mac=None,
                    tags=None,
                    uuid=None,
                )
                self.add(a_side_conn)
            # Add Connection from Z side connection Circuit to Device
            if endpoint_dev and endpoint_int:
                z_side_conn = self.conn(
                    src_device=_tc["circuit_id"],
                    src_port=_tc["circuit_id"],
                    src_type="circuit",
                    dst_device=endpoint_dev,
                    dst_port=endpoint_int,
                    dst_port_mac=(
                        self.d42_port_map[_tc["end_point_netport_fk"]]["hwaddress"]
                        if _tc["end_point_type"] == "Device"
                        else None
                    ),
                    dst_type="interface" if _tc["end_point_type"] == "Device Port" else "patch panel",
                    src_port_mac=None,
                    tags=None,
                    uuid=None,
                )
                self.add(z_side_conn)

    def check_dns(self):
        """Method to check if a Device has a DNS record and assign as primary if so."""
        for _device in self.store.get_all(model=dcim.Device):
            if not re.search(r"\s-\s\w+\s?\d+", _device.name) and not re.search(
                r"AP[A-F0-9]{4}\.[A-F0-9]{4}.[A-F0-9]{4}", _device.name
            ):
                self.set_primary_from_dns(dev_name=_device.name)
            else:
                self.job.logger.warning(f"Skipping {_device.name} due to invalid Device name.")
                continue

    def get_management_intf(self, dev_name: str):
        """Method to find a Device's management interface or create one if one doesn't exist.

        Args:
            dev_name (str): Name of Device to find Management interface.

        Returns:
            Port: DiffSyncModel Port object that's assumed to be Management interface if found. False if not found.
        """
        try:
            _intf = self.get(self.port, {"device": dev_name, "name": "mgmt0"})
        except ObjectNotFound:
            try:
                _intf = self.get(self.port, {"device": dev_name, "name": "management"})
            except ObjectNotFound:
                try:
                    _intf = self.get(self.port, {"device": dev_name, "name": "management0"})
                except ObjectNotFound:
                    try:
                        _intf = self.get(self.port, {"device": dev_name, "name": "Management"})
                    except ObjectNotFound:
                        return False
        return _intf

    def add_management_interface(self, dev_name: str):
        """Method to add a Management interface DiffSyncModel object.

        Args:
            dev_name (str): Name of Device to find Management interface.
        """
        _intf = self.port(
            name="Management",
            device=dev_name,
            type="other",
            enabled=True,
            description="Interface added by script for Management of device using DNS A record.",
            mode="access",
            mtu=1500,
            mac_addr="",
            custom_fields=self.device42.get_port_default_custom_fields(),
            tags=[],
            status="Active",
            uuid=None,
        )
        try:
            self.add(_intf)
            _device = self.get(self.device, dev_name)
            _device.add_child(_intf)
            return _intf
        except ObjectAlreadyExists as err:
            self.job.logger.warning(f"Management interface for {dev_name} already exists. {err}")

    def set_primary_from_dns(self, dev_name: str):
        """Method to resolve Device FQDNs A records into an IP and set primary IP for that Device to it if found.

            Checks if `use_dns` setting variable is `True`.

        Args:
            dev_name (str): Name of Device to perform DNS query on.
        """
        _devname = re.search(r"[a-zA-Z0-9\.\/\?\:\-_=#]+\.[a-zA-Z]{2,6}", dev_name)
        if _devname:
            _devname = _devname.group()
        else:
            return ""
        _a_record = get_dns_a_record(dev_name=_devname)
        if _a_record:
            self.job.logger.info(f"A record found for {_devname} {_a_record}.")
            _ip = self.find_ipaddr(address=_a_record)
            mgmt_intf = self.get_management_intf(dev_name=dev_name)
            if not mgmt_intf:
                mgmt_intf = self.add_management_interface(dev_name=dev_name)
            if not _ip:
                _ip = self.add_ipaddr(
                    address=f"{_a_record}/32", dev_name=dev_name, interface=mgmt_intf.name, namespace="Global"
                )
            if mgmt_intf and _ip.device != dev_name:
                _ip.device = dev_name
                _ip.interface = mgmt_intf.name
                _ip.primary = True
            else:
                _ip.primary = True
        else:
            self.job.logger.warning(f"A record not found for {_devname}.")

    def find_ipaddr(self, address: str):
        """Method to find IPAddress DiffSyncModel object."""
        for prefix in self.d42_subnet_map:
            subnet = ipaddress.ip_network(f"{prefix['network']}/{prefix['mask_bits']}")
            addr = ipaddress.ip_address(address)

            if addr in subnet:
                _addr = f"{addr}/{subnet.prefixlen}"
                try:
                    return self.get(self.ipaddr, {"address": _addr, "subnet": subnet.with_prefixlen})
                except ObjectNotFound:
                    pass
        return False

    def add_ipaddr(self, address: str, dev_name: str, interface: str, namespace: str):
        """Method to add IPAddress DiffSyncModel object if one isn't found.

        Used in conjunction with the `device42_use_dns` feature.
        """
        _ip = self.ipaddr(
            address=address,
            subnet=address if address != "" else "Global",
            namespace=namespace,
            available=False,
            device=dev_name,
            interface=interface,
            primary=True,
            label="",
            tags=[],
            custom_fields=self.d42_ipaddr_default_cfs,
            uuid=None,
        )
        self.add(_ip)
        return _ip

    def load_patch_panels_and_ports(self):
        """Load Device42 Patch Panels and Patch Panel Ports."""
        panels = self.device42.get_patch_panels()
        for panel in panels:
            _building, _room, _rack = None, None, None
            if PLUGIN_CFG.get("device42_hostname_mapping") and len(PLUGIN_CFG["device42_hostname_mapping"]) > 0:
                _building = get_site_from_mapping(device_name=panel["name"])
            if not _building and PLUGIN_CFG.get("device42_customer_is_facility") and panel["customer_fk"] is not None:
                _building = self.d42_customer_map[panel["customer_fk"]]["name"]
            if not _building and panel["building_fk"] is not None:
                _building = self.d42_building_map[panel["building_fk"]]["name"]
            if not _building and panel["calculated_building_fk"] is not None:
                _building = self.d42_building_map[panel["calculated_building_fk"]]["name"]
            if panel["room_fk"] is not None:
                _room = self.d42_room_map[panel["room_fk"]]["name"]
            if not _room and panel["calculated_room_fk"] is not None:
                _room = self.d42_room_map[panel["calculated_room_fk"]]["name"]
            if panel["rack_fk"] is not None:
                _rack = self.d42_rack_map[panel["rack_fk"]]["name"]
            if not _rack and panel["calculated_rack_fk"] is not None:
                _rack = self.d42_rack_map[panel["calculated_rack_fk"]]["name"]
            if _building is None and _room is None and _rack is None:
                if self.job.debug:
                    self.job.logger.debug(
                        f"Unable to determine Site, Room, or Rack for patch panel {panel['name']} so it will NOT be imported."
                    )
                continue
            self.load_vendor_and_model(hwmodel_name=panel["model_name"], manuf=panel["vendor"])
            try:
                new_pp = self.get(self.patchpanel, panel["name"])
            except ObjectNotFound:
                new_pp = self.patchpanel(
                    name=panel["name"],
                    in_service=panel["in_service"],
                    vendor=panel["vendor"],
                    model=panel["model_name"],
                    position=panel["position"],
                    orientation="front" if panel.get("orientation") == "Front" else "rear",
                    num_ports=panel["number_of_ports"],
                    rack=_rack,
                    serial_no=panel["serial_no"],
                    building=_building,
                    room=_room,
                    uuid=None,
                )
                self.add(new_pp)
                ind = 1
                while ind <= panel["number_of_ports"]:
                    if "LC" in panel["port_type"]:
                        port_type = "lc"
                    elif "FC" in panel["port_type"]:
                        port_type = "fc"
                    else:
                        port_type = "8p8c"
                    front_intf = self.patchpanelfrontport(
                        name=f"{ind}",
                        patchpanel=panel["name"],
                        port_type=port_type,
                        uuid=None,
                    )
                    rear_intf = self.patchpanelrearport(
                        name=f"{ind}",
                        patchpanel=panel["name"],
                        port_type=port_type,
                        uuid=None,
                    )
                    try:
                        self.add(front_intf)
                        self.add(rear_intf)
                    except ObjectAlreadyExists as err:
                        if self.job.debug:
                            self.job.logger.warning(
                                f"Patch panel port {ind} for {panel['name']} is already loaded. {err}"
                            )
                    ind = ind + 1

    def load(self):
        """Load data from Device42."""
        self.load_buildings()
        self.load_rooms()
        self.load_racks()
        self.load_vrfgroups()
        self.load_vlans()
        self.load_subnets()
        self.load_devices_and_clusters()
        self.assign_version_to_master_devices()
        self.load_ports()
        self.load_ip_addresses()
        if "device42_use_dns" in PLUGIN_CFG and is_truthy(PLUGIN_CFG.get("device42_use_dns")):
            self.job.logger.info("Checking DNS entries for all loaded Devices.")
            self.check_dns()
        self.load_providers_and_circuits()
        self.load_patch_panels_and_ports()
        # self.load_connections()
