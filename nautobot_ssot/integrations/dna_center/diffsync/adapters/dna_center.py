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

    def build_dnac_location_map(self, locations: List[dict]):  # pylint: disable=too-many-statements, too-many-branches
        """Build out the DNA Center location structure based off DNAC information or Job location_map field.

        Args:
            locations (List[dict]): List of Locations from DNA Center to be processed.
        """
        # build initial mapping of IDs to location name
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
                "loc_type": "area",
                "parent": None,
                "parent_of_parent": None,
            }

        # add parent name for each location
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
            if location["name"] in self.job.location_map and self.job.location_map[location["name"]].get("parent"):
                parent_name = self.job.location_map[location["name"]]["parent"]
            self.dnac_location_map[loc_id]["parent"] = parent_name

        # add parent of parent to the mapping
        floors = []
        for location in locations:  # pylint: disable=too-many-nested-blocks
            if (
                not settings.PLUGINS_CONFIG["nautobot_ssot"].get("dna_center_import_global")
                and location["name"] == "Global"
            ):
                continue
            loc_id = location["id"]
            loc_name = location["name"]
            parent_id = location.get("parentId")
            if self.dnac_location_map.get(parent_id):
                self.dnac_location_map[loc_id]["parent_of_parent"] = self.dnac_location_map[parent_id]["parent"]
            parent_name = self.dnac_location_map[loc_id]["parent"]
            for info in location["additionalInfo"]:
                if info["attributes"].get("type"):
                    self.dnac_location_map[loc_id]["loc_type"] = info["attributes"]["type"]
                    if info["attributes"]["type"] in ["area", "building"]:
                        if info["attributes"]["type"] == "building":
                            self.building_map[loc_id] = location
                            if self.job.location_map.get(parent_name) and self.job.location_map[parent_name].get(
                                "parent"
                            ):
                                self.dnac_location_map[loc_id]["parent_of_parent"] = self.job.location_map[parent_name][
                                    "parent"
                                ]
                        if self.job.location_map.get(loc_name):
                            if self.job.location_map[loc_name].get("parent"):
                                self.dnac_location_map[loc_id]["parent"] = self.job.location_map[loc_name]["parent"]
                            if self.job.location_map[loc_name].get("area_parent"):
                                self.dnac_location_map[loc_id]["parent_of_parent"] = self.job.location_map[loc_name][
                                    "area_parent"
                                ]
                    elif info["attributes"]["type"] == "floor":
                        floors.append(location)
                        if self.dnac_location_map.get(parent_id):
                            self.dnac_location_map[loc_id]["parent"] = self.dnac_location_map[parent_id]["name"]
                            self.dnac_location_map[loc_id]["parent_of_parent"] = self.dnac_location_map[parent_id][
                                "parent"
                            ]
                        if self.job.location_map.get(parent_name) and self.dnac_location_map[parent_id].get("name"):
                            self.dnac_location_map[loc_id]["parent"] = self.dnac_location_map[parent_id]["name"]
                        if self.job.location_map.get(parent_name) and self.dnac_location_map[parent_id].get("parent"):
                            self.dnac_location_map[loc_id]["parent_of_parent"] = self.dnac_location_map[parent_id][
                                "parent"
                            ]
        if self.job.debug:
            self.job.logger.debug(f"Generated DNAC Location Map: {self.dnac_location_map}")
        return floors

    def load_controller_locations(self):
        """Load location data for Controller specified in Job form."""
        if not self.job.dnac.location:
            self.job.logger.error(
                f"Unable to find Location assigned to {self.job.dnac.name} so skipping loading of Locations for Controller."
            )
            return

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
            self.job.dnac.location.parent
            and self.job.dnac.location.parent.parent
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
                    "parent_of_parent": (
                        self.job.dnac.location.parent.parent.parent.name
                        if self.job.dnac.location.parent.parent and self.job.dnac.location.parent.parent.parent
                        else None
                    ),
                },
                attrs={"uuid": None},
            )
        if (
            self.job.dnac.location.parent
            and self.job.dnac.location.parent.parent
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
                    "parent_of_parent": (
                        self.job.dnac.location.parent.parent.parent.parent.name
                        if self.job.dnac.location.parent.parent.parent
                        and self.job.dnac.location.parent.parent.parent.parent
                        else None
                    ),
                },
                attrs={"uuid": None},
            )

    def load_area(self, area: str, area_parent: Optional[str] = None, area_parent_of_parent: Optional[str] = None):
        """Load area from DNAC into DiffSync model.

        Args:
            area (str): Name of area to be loaded.
            area_parent (Optional[str], optional): Name of area's parent if defined. Defaults to None.
            area_parent_of_parent (Optional[str], optional): Name of area's parent of parent if defined. Defaults to None.
        """
        self.get_or_instantiate(
            self.area,
            ids={"name": area, "parent": area_parent, "parent_of_parent": area_parent_of_parent},
            attrs={"uuid": None},
        )

    def load_building(self, building: dict, area_name: Optional[str] = None, area_parent_name: Optional[str] = None):
        """Load building data from DNAC into DiffSync model.

        Args:
            building (dict): Dictionary containing location information about a building.
            area_name (str): Parent area for building.
            area_parent_name (str): Parent of parent area for building.
        """
        bldg_name = self.dnac_location_map[building["id"]]["name"]
        if self.job.debug:
            self.job.logger.info(
                f"Loading {self.job.building_loctype.name} {bldg_name} in {area_name} with parent {area_parent_name}. {building}"
            )
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
                "metadata": True,
            },
        )

    def load_floor(self, floor_name: str, bldg_name: str, area_name: str):
        """Load floor data from DNAC into DiffSync model.

        Args:
            floor_name (str): Name of Floor location to be loaded.
            bldg_name (str): Name of Building location that Floor is a part of.
            area_name (str): Name of Area that Building location resides in.
        """
        if bldg_name not in floor_name:
            floor_name = f"{bldg_name} - {floor_name}"
        if self.job.debug:
            self.job.logger.info(f"Loading floor {floor_name} in {area_name} area.")
        try:
            parent = self.get(self.building, {"name": bldg_name, "area": area_name})
            new_floor, loaded = self.get_or_instantiate(
                self.floor,
                ids={"name": floor_name, "building": bldg_name, "area": area_name},
                attrs={
                    "tenant": self.tenant.name if self.tenant else None,
                    "metadata": True,
                },
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
            dev_role = "Unknown"
            vendor = "Cisco"
            platform = self.get_device_platform(dev)
            if not PLUGIN_CFG.get("dna_center_import_merakis") and platform == "cisco_meraki":
                continue
            if platform == "unknown":
                self.job.logger.warning(f"Device {dev['hostname']} is missing Platform so will be skipped.")
                dev["field_validation"] = {
                    "reason": "Failed due to missing platform.",
                }
                self.failed_import_devices.append(dev)
                continue
            if not dev.get("hostname"):
                if self.job.debug:
                    self.job.logger.warning(f"Device {dev['id']} is missing hostname so will be skipped.")
                dev["field_validation"] = {
                    "reason": "Failed due to missing hostname.",
                }
                self.failed_import_devices.append(dev)
                continue
            if dev.get("type") and "Juniper" in dev["type"]:
                vendor = "Juniper"
            dev_role = self.get_device_role(dev)
            dev_details = self.conn.get_device_detail(dev_id=dev["id"])
            loc_data = {}
            if dev_details and dev_details.get("siteHierarchyGraphId"):
                locations = dev_details["siteHierarchyGraphId"].lstrip("/").rstrip("/").split("/")
                # remove Global if not importing Global
                if not settings.PLUGINS_CONFIG["nautobot_ssot"].get("dna_center_import_global"):
                    locations.pop(0)
                loc_found = [loc in self.dnac_location_map for loc in locations]
                if not all(loc_found):
                    self.job.logger.error(
                        f"Device {dev['hostname']} has unknown location in hierarchy so will not be imported."
                    )
                    dev["field_validation"] = {
                        "reason": "Invalid location information found.",
                        "device_details": dev_details,
                        "location_data": loc_data,
                    }
                    self.failed_import_devices.append(dev)
                    continue
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
                location_ids = dev_details["siteHierarchyGraphId"].lstrip("/").rstrip("/").split("/")
                floor_name = None
                if loc_data.get("floor"):
                    floor_name = self.dnac_location_map[location_ids[-1]]["name"]
                    if loc_data["building"] not in loc_data["floor"]:
                        bldg_name = self.dnac_location_map[location_ids[-1]]["parent"]
                        floor_name = f"{bldg_name} - {floor_name}"
                    location_ids.pop(-1)
                building_name = self.dnac_location_map[location_ids[-1]]["name"]
                area_name = self.dnac_location_map[location_ids[-1]]["parent"]
                new_dev = self.device(
                    name=dev["hostname"],
                    status="Active" if dev.get("reachabilityStatus") != "Unreachable" else "Offline",
                    role=dev_role,
                    vendor=vendor,
                    model=self.conn.get_model_name(models=dev["platformId"]) if dev.get("platformId") else "Unknown",
                    area=area_name,
                    site=building_name,
                    floor=floor_name,
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
        floor_id = ""
        location_ids = dev_details["siteHierarchyGraphId"].lstrip("/").rstrip("/").split("/")
        if not settings.PLUGINS_CONFIG["nautobot_ssot"].get("dna_center_import_global"):
            location_ids.pop(0)
        if loc_data.get("floor"):
            floor_id = location_ids.pop()
        building_id = location_ids.pop()
        areas = location_ids

        for area_id in areas:
            if self.dnac_location_map.get(area_id):
                area_name = self.dnac_location_map[area_id]["name"]
                area_parent = self.dnac_location_map[area_id]["parent"]
                area_parent_of_parent = self.dnac_location_map[area_id]["parent_of_parent"]

                if self.job.debug:
                    self.job.logger.debug(f"Loading area {area_name} in {area_parent}.")
                self.load_area(area=area_name, area_parent=area_parent, area_parent_of_parent=area_parent_of_parent)
            else:
                self.job.logger.warning(f"Unable to find area {area_id} in DNAC location map.")
        self.load_building(
            building=self.building_map[building_id],
            area_name=self.dnac_location_map[building_id]["parent"],
            area_parent_name=self.dnac_location_map[building_id]["parent_of_parent"],
        )
        if loc_data.get("floor"):
            self.load_floor(
                floor_name=self.dnac_location_map[floor_id]["name"],
                bldg_name=self.dnac_location_map[floor_id]["parent"],
                area_name=self.dnac_location_map[building_id]["parent"],
            )

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
            if not dev.get("softwareType") and dev.get("type"):
                for series in ["2700", "2800", "3800", "9120", "9124", "9130", "9136", "9166", "9115"]:
                    if series in dev["type"]:
                        platform = "cisco_ios"
                        break

                for series in ["8540", "1850", "1562"]:
                    if series in dev["type"]:
                        platform = "cisco_aireos"
                        break

            if (
                (dev.get("family") and "Meraki" in dev["family"])
                or (dev.get("platformId") and dev["platformId"].startswith(("MX", "MS", "MR", "Z")))
                or (dev.get("errorDescription") and "Meraki" in dev["errorDescription"])
            ):
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
            port_type = self.conn.get_port_type(port_info=port)
            port_status = self.conn.get_port_status(port_info=port)
            new_port, loaded = self.get_or_instantiate(
                self.port,
                ids={
                    "name": port["portName"],
                    "device": dev.name,
                },
                attrs={
                    "description": port["description"],
                    "enabled": True if port["adminStatus"] == "UP" else False,
                    "port_type": port_type,
                    "port_mode": "tagged" if port["portMode"] == "trunk" else "access",
                    "mac_addr": port["macAddress"].upper() if port.get("macAddress") else None,
                    "mtu": port["mtu"] if port.get("mtu") else 1500,
                    "status": port_status,
                    "uuid": None,
                },
            )
            if loaded:
                if self.job.debug:
                    self.job.logger.info(f"Loaded port {port['portName']} for {dev.name}. {port}")
                dev.add_child(new_port)
                if port.get("addresses"):
                    for addr in port["addresses"]:
                        host = addr["address"]["ipAddress"]["address"]
                        mask_length = netmask_to_cidr(addr["address"]["ipMask"]["address"])
                        prefix = ipaddress_interface(f"{host}/{mask_length}", "network.with_prefixlen")
                        primary = bool(addr["address"]["ipAddress"]["address"] == mgmt_addr)
                        self.load_ip_address(
                            host=host,
                            mask_length=mask_length,
                            prefix=prefix,
                        )
                        self.load_ipaddress_to_interface(
                            host=host,
                            device=dev.name if dev.name else "",
                            port=port["portName"],
                            primary=primary,
                        )
            else:
                self.job.logger.warning(f"Duplicate port attempting to be loaded, {port['portName']} for {dev.name}")

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

    def load_ipaddress_to_interface(self, host: str, device: str, port: str, primary: bool):
        """Load DNAC IPAddressOnInterface DiffSync model with specified data.

        Args:
            host (str): Host IP Address in mapping.
            device (str): Device that IP resides on.
            port (str): Interface that IP is configured on.
            primary (str): Whether the IP is primary IP for assigned device. Defaults to False.
        """
        self.get_or_instantiate(
            self.ip_on_intf,
            ids={"host": host, "device": device, "port": port},
            attrs={"primary": primary},
        )

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
