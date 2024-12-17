"""Nautobot SSoT for Cisco DNA Center Adapter for DNA Center SSoT plugin."""

import json
from typing import List, Optional

from diffsync import Adapter
from diffsync.exceptions import ObjectNotFound
from django.conf import settings
from django.core.exceptions import ValidationError
from nautobot.tenancy.models import Tenant
from netutils.ip import ipaddress_interface, netmask_to_cidr
from netutils.lib_mapper import DNA_CENTER_LIB_MAPPER

from nautobot_ssot.integrations.dna_center.constants import PLUGIN_CFG
from nautobot_ssot.integrations.dna_center.diffsync.models.dna_center import (
    DnaCenterArea,
    DnaCenterBuilding,
    DnaCenterDevice,
    DnaCenterFloor,
    DnaCenterIPAddress,
    DnaCenterIPAddressonInterface,
    DnaCenterPort,
    DnaCenterPrefix,
)
from nautobot_ssot.integrations.dna_center.utils.dna_center import DnaCenterClient
from nautobot_ssot.utils import parse_hostname_for_role


class DnaCenterAdapter(Adapter):
    """DiffSync adapter for DNA Center."""

    area = DnaCenterArea
    building = DnaCenterBuilding
    floor = DnaCenterFloor
    device = DnaCenterDevice
    port = DnaCenterPort
    prefix = DnaCenterPrefix
    ipaddress = DnaCenterIPAddress
    ip_on_intf = DnaCenterIPAddressonInterface

    top_level = ["area", "building", "device", "prefix", "ipaddress", "ip_on_intf"]

    def __init__(self, *args, job, sync=None, client: DnaCenterClient, tenant: Tenant, **kwargs):
        """Initialize DNA Center.

        Args:
            job (Union[DataSource, DataTarget]): DNA Center job.
            sync (object, optional): DNA Center DiffSync. Defaults to None.
            client (DnaCenterClient): DNA Center API client connection object.
            tenant (Tenant): Tenant to attach to imported objects. Can be set to None for no Tenant to be attached.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.conn = client
        self.failed_import_devices = []
        self.dnac_location_map = {}
        self.building_map = {}
        self.floors = []
        self.tenant = tenant

    def load_locations(self):
        """Load location data from DNA Center into DiffSync models."""
        self.load_controller_locations()
        locations = self.conn.get_locations()
        if locations:
            self.floors = self.build_dnac_location_map(locations)
        else:
            self.job.logger.error("No location data was returned from DNA Center. Unable to proceed.")

    def build_dnac_location_map(self, locations: List[dict]):  # pylint: disable=too-many-branches
        """Build out the DNA Center location structure based off DNAC information or Job location_map field.

        Args:
            locations (List[dict]): List of Locations from DNA Center to be separated.
        """
        floors = []
        for location in locations:
            if (
                not settings.PLUGINS_CONFIG["nautobot_ssot"].get("dna_center_import_global")
                and location["name"] == "Global"
            ):
                continue
            if location["name"] in self.job.location_map and self.job.location_map[location["name"]].get("name"):
                loc_name = self.job.location_map[location["name"]]["name"]
            else:
                loc_name = location["name"]
            self.dnac_location_map[location["id"]] = {
                "name": loc_name,
                "parent": None,
                "parent_of_parent": None,
            }
        for location in locations:  # pylint: disable=too-many-nested-blocks
            loc_id = location["id"]
            loc_name = location["name"]
            parent_id, parent_name = None, None
            if location.get("parentId"):
                parent_id = location["parentId"]
                if self.dnac_location_map.get(parent_id):
                    parent_name = self.dnac_location_map[parent_id]["name"]
            if not settings.PLUGINS_CONFIG["nautobot_ssot"].get("dna_center_import_global"):
                if loc_name == "Global":
                    continue
                if parent_name == "Global":
                    parent_name = None
            self.dnac_location_map[loc_id]["parent"] = parent_name
            for info in location["additionalInfo"]:
                if info["attributes"].get("type"):
                    self.dnac_location_map[loc_id]["loc_type"] = info["attributes"]["type"]
                    if info["attributes"]["type"] in ["area", "building"]:
                        if info["attributes"]["type"] == "building":
                            self.building_map[loc_id] = location
                        if info["attributes"]["type"] == "building" and loc_name in self.job.location_map:
                            if self.job.location_map[loc_name].get("parent"):
                                self.dnac_location_map[loc_id]["parent"] = self.job.location_map[loc_name]["parent"]
                            if self.job.location_map[loc_name].get("area_parent"):
                                self.dnac_location_map[loc_id]["parent_of_parent"] = self.job.location_map[loc_name][
                                    "area_parent"
                                ]
                            else:
                                self.dnac_location_map[loc_id]["parent_of_parent"] = parent_name
                        if info["attributes"]["type"] == "floor":
                            floors.append(location)
                            if parent_name in self.job.location_map and self.dnac_location_map[parent_id].get("name"):
                                self.dnac_location_map[loc_id]["parent"] = self.dnac_location_map[parent_id]["name"]
        return floors

    def load_controller_locations(self):
        """Load location data for Controller specified in Job form."""
        if self.job.dnac.location.location_type == self.job.floor_loctype:
            self.get_or_instantiate(
                self.floor,
                ids={
                    "name": self.job.dnac.location.name,
                    "building": self.job.dnac.location.parent.name,
                },
                attrs={
                    "tenant": self.job.dnac.location.tenant.name if self.job.dnac.location.tenant else None,
                    "uuid": None,
                },
            )
        if (
            self.job.dnac.location.parent.parent
            and self.job.dnac.location.parent.parent.location_type == self.job.building_loctype
        ):
            self.get_or_instantiate(
                self.building,
                ids={
                    "name": self.job.dnac.location.parent.parent.name,
                    "parent": (
                        self.job.dnac.location.parent.parent.parent.name
                        if self.job.dnac.location.parent.parent.parent
                        else None
                    ),
                },
                attrs={"uuid": None},
            )

        if self.job.dnac.location.location_type == self.job.building_loctype:
            self.get_or_instantiate(
                self.building,
                ids={
                    "name": self.job.dnac.location.name,
                    "area": self.job.dnac.location.parent.name if self.job.dnac.location.parent else None,
                },
                attrs={
                    "address": self.job.dnac.location.physical_address,
                    "area_parent": (
                        self.job.dnac.location.parent.parent.name
                        if self.job.dnac.location.parent and self.job.dnac.location.parent.parent
                        else None
                    ),
                    "latitude": str(self.job.dnac.location.latitude),
                    "longitude": str(self.job.dnac.location.longitude),
                    "tenant": self.job.dnac.location.tenant.name if self.job.dnac.location.tenant else None,
                    "uuid": None,
                },
            )
        if self.job.dnac.location.parent.location_type == self.job.area_loctype:
            self.get_or_instantiate(
                self.area,
                ids={
                    "name": self.job.dnac.location.parent.name,
                    "parent": (
                        self.job.dnac.location.parent.parent.name if self.job.dnac.location.parent.parent else None
                    ),
                },
                attrs={"uuid": None},
            )
        if (
            self.job.dnac.location.parent.parent
            and self.job.dnac.location.parent.parent.location_type == self.job.area_loctype
        ):
            self.get_or_instantiate(
                self.area,
                ids={
                    "name": self.job.dnac.location.parent.parent.name,
                    "parent": (
                        self.job.dnac.location.parent.parent.parent.name
                        if self.job.dnac.location.parent.parent.parent
                        else None
                    ),
                },
                attrs={"uuid": None},
            )

    def load_area(self, area: str, area_parent: Optional[str] = None):
        """Load area from DNAC into DiffSync model.

        Args:
            area (str): Name of area to be loaded.
            area_parent (Optional[str], optional): Name of area's parent if defined. Defaults to None.
        """
        self.get_or_instantiate(self.area, ids={"name": area, "parent": area_parent}, attrs={"uuid": None})

    def load_building(self, building: dict, area_name: Optional[str] = None, area_parent_name: Optional[str] = None):
        """Load building data from DNAC into DiffSync model.

        Args:
            building (dict): Dictionary containing location information about a building.
        """
        if self.job.debug:
            self.job.logger.info(f"Loading {self.job.building_loctype.name} {building['name']}. {building}")
        bldg_name = building["name"]
        address, _ = self.conn.find_address_and_type(info=building["additionalInfo"])
        latitude, longitude = self.conn.find_latitude_and_longitude(info=building["additionalInfo"])
        self.get_or_instantiate(
            self.building,
            ids={"name": bldg_name, "area": area_name},
            attrs={
                "address": address if address else "",
                "area_parent": area_parent_name,
                "latitude": latitude[:9].rstrip("0"),
                "longitude": longitude[:7].rstrip("0"),
                "tenant": self.tenant.name if self.tenant else None,
                "uuid": None,
            },
        )

    def load_floor(self, floor_name: str, bldg_name: str, area_name: str):
        """Load floor data from DNAC into DiffSync model.

        Args:
            floor_name (str): Name of Floor location to be loaded.
            bldg_name (str): Name of Building location that Floor is a part of.
            area_name (str): Name of Area that Building location resides in.
        """
        if self.job.debug:
            self.job.logger.info(f"Loading floor {floor_name} in {bldg_name} building in {area_name} area.")
        floor_name = f"{bldg_name} - {floor_name}"
        try:
            parent = self.get(self.building, {"name": bldg_name, "area": area_name})
            new_floor, loaded = self.get_or_instantiate(
                self.floor,
                ids={"name": floor_name, "building": bldg_name},
                attrs={"tenant": self.tenant.name if self.tenant else None, "uuid": None},
            )
            if loaded:
                parent.add_child(new_floor)
        except ObjectNotFound as err:
            self.job.logger.warning(
                f"Unable to find {self.job.building_loctype.name} {bldg_name} for {self.job.floor_loctype.name} {floor_name}. {err}"
            )

    def load_devices(self):
        """Load Device data from DNA Center info DiffSync models."""
        devices = self.conn.get_devices()
        for dev in devices:
            if not PLUGIN_CFG.get("dna_center_import_merakis") and (
                (dev.get("family") and "Meraki" in dev["family"])
                or (dev.get("errorDescription") and "Meraki" in dev["errorDescription"])
            ):
                continue
            dev_role = "Unknown"
            vendor = "Cisco"
            if not dev.get("hostname"):
                if self.job.debug:
                    self.job.logger.warning(f"Device {dev['id']} is missing hostname so will be skipped.")
                dev["field_validation"] = {
                    "reason": "Failed due to missing hostname.",
                }
                self.failed_import_devices.append(dev)
                continue
            dev_role = self.get_device_role(dev)
            platform = self.get_device_platform(dev)
            if platform == "unknown":
                self.job.logger.warning(f"Device {dev['hostname']} is missing Platform so will be skipped.")
                dev["field_validation"] = {
                    "reason": "Failed due to missing platform.",
                }
                self.failed_import_devices.append(dev)
                continue
            if dev.get("type") and "Juniper" in dev["type"]:
                vendor = "Juniper"
            dev_details = self.conn.get_device_detail(dev_id=dev["id"])
            loc_data = {}
            if dev_details and dev_details.get("siteHierarchyGraphId"):
                loc_data = self.conn.parse_site_hierarchy(
                    location_map=self.dnac_location_map, site_hier=dev_details["siteHierarchyGraphId"]
                )
            if (
                (dev_details and not dev_details.get("siteHierarchyGraphId"))
                or loc_data.get("building") == "Unassigned"
                or not loc_data.get("building")
            ):
                if self.job.debug:
                    self.job.logger.warning(f"Device {dev['hostname']} is missing building so will not be imported.")
                dev["field_validation"] = {
                    "reason": "Missing building assignment.",
                    "device_details": dev_details,
                    "location_data": loc_data,
                }
                self.failed_import_devices.append(dev)
                continue
            self.load_device_location_tree(dev_details, loc_data)
            try:
                if self.job.debug:
                    self.job.logger.info(
                        f"Loading device {dev['hostname'] if dev.get('hostname') else dev['id']}. {dev}"
                    )
                device_found = self.get(self.device, dev["hostname"])
                if device_found:
                    if self.job.debug:
                        self.job.logger.warning(
                            f"Duplicate device attempting to be loaded for {dev['hostname']} with ID: {dev['id']} so will not be imported."
                        )
                    dev["field_validation"] = {
                        "reason": "Failed due to duplicate device found.",
                        "device_details": dev_details,
                        "location_data": loc_data,
                    }
                    self.failed_import_devices.append(dev)
                    continue
            except ObjectNotFound:
                new_dev = self.device(
                    name=dev["hostname"],
                    status="Active" if dev.get("reachabilityStatus") != "Unreachable" else "Offline",
                    role=dev_role,
                    vendor=vendor,
                    model=self.conn.get_model_name(models=dev["platformId"]) if dev.get("platformId") else "Unknown",
                    site=loc_data["building"],
                    floor=f"{loc_data['building']} - {loc_data['floor']}" if loc_data.get("floor") else None,
                    serial=dev["serialNumber"] if dev.get("serialNumber") else "",
                    version=dev.get("softwareVersion"),
                    platform=platform,
                    tenant=self.tenant.name if self.tenant else None,
                    controller_group=self.job.controller_group.name,
                    uuid=None,
                )
                try:
                    self.add(new_dev)
                    self.load_ports(device_id=dev["id"], dev=new_dev, mgmt_addr=dev["managementIpAddress"])
                except ValidationError as err:
                    if self.job.debug:
                        self.job.logger.warning(f"Unable to load device {dev['hostname']}. {err}")
                    dev["field_validation"] = {
                        "reason": f"Failed validation. {err}",
                        "device_details": dev_details,
                        "location_data": loc_data,
                    }
                    self.failed_import_devices.append(dev)

    def load_device_location_tree(self, dev_details: dict, loc_data: dict):
        """Load Device locations into DiffSync models for Floor, Building, and Areas.

        Args:
            dev_details (dict): Dictionary of Device information.
            loc_data (dict): Location data for the Device.
        """
        reversed_areas = loc_data["areas"][::-1]
        for area in reversed_areas:
            item_index = reversed_areas.index(area)
            if item_index + 2 <= len(loc_data["areas"]):
                self.load_area(area=area, area_parent=reversed_areas[item_index + 1])
            else:
                self.load_area(area=area, area_parent=None)
        if loc_data.get("floor"):
            building_id = dev_details["siteHierarchyGraphId"].lstrip("/").rstrip("/").split("/")[-2]
            self.load_building(building=self.building_map[building_id], area_name=loc_data["areas"][-1])
            self.load_floor(
                floor_name=loc_data["floor"], bldg_name=loc_data["building"], area_name=loc_data["areas"][-1]
            )
        else:
            building_id = dev_details["siteHierarchyGraphId"].lstrip("/").rstrip("/").split("/")[-1]
            self.load_building(building=self.building_map[building_id], area_name=loc_data["areas"][-1])

    def get_device_role(self, dev):
        """Get Device Role from Job Hostname map or DNA Center 'role'.

        Args:
            dev (dict): Dictionary of information about Device from DNA Center.

        Returns:
            str: Device role that has been determined from Hostname map or DNA Center information.
        """
        if self.job.hostname_map:
            dev_role = parse_hostname_for_role(
                hostname_map=self.job.hostname_map, device_hostname=dev["hostname"], default_role="Unknown"
            )
        else:
            dev_role = dev["role"]
        return dev_role

    def get_device_platform(self, dev):
        """Get Device Platform from Job information.

        Args:
            dev (dict): Dictionary of information about Device from DNA Center.

        Returns:
            str: Device platform that has been determined from DNA Center information.
        """
        platform = "unknown"
        if dev["softwareType"] in DNA_CENTER_LIB_MAPPER:
            platform = DNA_CENTER_LIB_MAPPER[dev["softwareType"]]
        else:
            if not dev.get("softwareType") and dev.get("type") and ("3800" in dev["type"] or "9130" in dev["type"]):
                platform = "cisco_ios"
            if not dev.get("softwareType") and dev.get("family") and "Meraki" in dev["family"]:
                platform = "cisco_meraki"
        return platform

    def load_ports(self, device_id: str, dev: DnaCenterDevice, mgmt_addr: str = ""):
        """Load port info from DNAC into Port DiffSyncModel.

        Args:
            device_id (str): ID for Device in DNAC to retrieve ports for.
            dev (DnaCenterDevice): Device associated with ports.
            mgmt_addr (str): Management IP address for device.
        """
        ports = self.conn.get_port_info(device_id=device_id)
        for port in ports:
            try:
                found_port = self.get(
                    self.port,
                    {
                        "name": port["portName"],
                        "device": dev.name,
                        "mac_addr": port["macAddress"].upper() if port.get("macAddress") else None,
                    },
                )
                if found_port and self.job.debug:
                    self.job.logger.warning(
                        f"Duplicate port attempting to be loaded, {port['portName']} for {dev.name}"
                    )
                continue
            except ObjectNotFound:
                if self.job.debug:
                    self.job.logger.info(f"Loading port {port['portName']} for {dev.name}. {port}")
                port_type = self.conn.get_port_type(port_info=port)
                port_status = self.conn.get_port_status(port_info=port)
                new_port = self.port(
                    name=port["portName"],
                    device=dev.name if dev.name else "",
                    description=port["description"],
                    enabled=True if port["adminStatus"] == "UP" else False,
                    port_type=port_type,
                    port_mode="tagged" if port["portMode"] == "trunk" else "access",
                    mac_addr=port["macAddress"].upper() if port.get("macAddress") else None,
                    mtu=port["mtu"] if port.get("mtu") else 1500,
                    status=port_status,
                    uuid=None,
                )
                try:
                    self.add(new_port)
                    dev.add_child(new_port)

                    if port.get("addresses"):
                        for addr in port["addresses"]:
                            host = addr["address"]["ipAddress"]["address"]
                            mask_length = netmask_to_cidr(addr["address"]["ipMask"]["address"])
                            prefix = ipaddress_interface(f"{host}/{mask_length}", "network.with_prefixlen")
                            if addr["address"]["ipAddress"]["address"] == mgmt_addr:
                                primary = True
                            else:
                                primary = False
                            self.load_ip_address(
                                host=host,
                                mask_length=mask_length,
                                prefix=prefix,
                            )
                            self.load_ipaddress_to_interface(
                                host=host,
                                prefix=prefix,
                                device=dev.name if dev.name else "",
                                port=port["portName"],
                                primary=primary,
                            )
                except ValidationError as err:
                    self.job.logger.warning(f"Unable to load port {port['portName']} for {dev.name}. {err}")

    def load_ip_address(self, host: str, mask_length: int, prefix: str):
        """Load IP Address info from DNAC into IPAddress DiffSyncModel.

        Args:
            host (str): Host IP Address to be loaded.
            mask_length (int): Mask length for IPAddress.
            prefix (str): Parent prefix for IPAddress.
        """
        if self.tenant:
            namespace = self.tenant.name
        else:
            namespace = "Global"
        try:
            self.get(self.prefix, {"prefix": prefix, "namespace": namespace})
        except ObjectNotFound:
            new_prefix = self.prefix(
                prefix=prefix,
                namespace=namespace,
                tenant=self.tenant.name if self.tenant else None,
                uuid=None,
            )
            self.add(new_prefix)
        try:
            ip_found = self.get(self.ipaddress, {"host": host, "namespace": namespace})
            if ip_found and self.job.debug:
                self.job.logger.warning(f"Duplicate IP Address attempting to be loaded: {host} in {prefix}")
        except ObjectNotFound:
            if self.job.debug:
                self.job.logger.info(f"Loading IP Address {host}.")
            new_ip = self.ipaddress(
                host=host,
                mask_length=mask_length,
                namespace=namespace,
                tenant=self.tenant.name if self.tenant else None,
                uuid=None,
            )
            self.add(new_ip)

    def load_ipaddress_to_interface(self, host: str, prefix: str, device: str, port: str, primary: bool):
        """Load DNAC IPAddressOnInterface DiffSync model with specified data.

        Args:
            host (str): Host IP Address in mapping.
            prefix (str): Parent prefix for host IP Address.
            device (str): Device that IP resides on.
            port (str): Interface that IP is configured on.
            primary (str): Whether the IP is primary IP for assigned device. Defaults to False.
        """
        try:
            self.get(self.ip_on_intf, {"host": host, "prefix": prefix, "device": device, "port": port})
        except ObjectNotFound:
            new_ipaddr_to_interface = self.ip_on_intf(host=host, device=device, port=port, primary=primary, uuid=None)
            self.add(new_ipaddr_to_interface)

    def load(self):
        """Load data from DNA Center into DiffSync models."""
        # add global prefix to be catchall
        global_prefix = self.prefix(
            prefix="0.0.0.0/0",
            namespace=self.tenant.name if self.tenant else "Global",
            tenant=self.tenant.name if self.tenant else None,
            uuid=None,
        )
        self.add(global_prefix)

        self.load_locations()
        self.load_devices()
        if PLUGIN_CFG.get("dna_center_show_failures"):
            if self.failed_import_devices:
                self.job.logger.warning(
                    f"List of {len(self.failed_import_devices)} devices that were unable to be loaded. {json.dumps(self.failed_import_devices, indent=2)}"
                )
            else:
                self.job.logger.info("There weren't any failed device loads. Congratulations!")
