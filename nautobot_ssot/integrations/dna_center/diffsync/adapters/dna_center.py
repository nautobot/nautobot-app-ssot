"""Nautobot SSoT for Cisco DNA Center Adapter for DNA Center SSoT plugin."""

from typing import List
import json
from netutils.ip import ipaddress_interface, netmask_to_cidr
from diffsync import DiffSync
from diffsync.exceptions import ObjectNotFound
from django.conf import settings
from django.core.exceptions import ValidationError
from nautobot.tenancy.models import Tenant

from nautobot_ssot_dna_center.constants import DNAC_PLATFORM_MAPPER, PLUGIN_CFG
from nautobot_ssot_dna_center.diffsync.models.dna_center import (
    DnaCenterArea,
    DnaCenterBuilding,
    DnaCenterDevice,
    DnaCenterFloor,
    DnaCenterPrefix,
    DnaCenterIPAddress,
    DnaCenterPort,
    DnaCenterIPAddressonInterface,
)
from nautobot_ssot_dna_center.utils.dna_center import DnaCenterClient


class DnaCenterAdapter(DiffSync):
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

    def __init__(self, *args, job=None, sync=None, client: DnaCenterClient, tenant: Tenant, **kwargs):
        """Initialize DNA Center.

        Args:
            job (object, optional): DNA Center job. Defaults to None.
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
        self.tenant = tenant

    def load_locations(self):
        """Load location data from DNA Center into DiffSync models."""
        locations = self.conn.get_locations()
        if locations:
            # to ensure we process locations in the appropriate order we need to split them into their own list of locations
            self.dnac_location_map = self.build_dnac_location_map(locations)
            areas, buildings, floors = self.parse_and_sort_locations(locations)
            self.load_areas(areas)
            self.load_buildings(buildings)
            self.load_floors(floors)
        else:
            self.job.logger.error("No location data was returned from DNAC. Unable to proceed.")

    def load_areas(self, areas: List[dict]):
        """Load areas from DNAC into DiffSync model.

        Args:
            areas (List[dict]): List of dictionaries containing location information about a building.
        """
        for location in areas:
            if not settings.PLUGINS_CONFIG["nautobot_ssot_dna_center"].get("import_global"):
                if location["name"] == "Global":
                    continue
            if self.job.debug:
                self.job.logger.info(f"Loading area {location['name']}. {location}")
            parent_name = None
            if location.get("parentId") and location["parentId"] in self.dnac_location_map:
                parent_name = self.dnac_location_map[location["parentId"]]["name"]
                self.dnac_location_map[location["id"]]["parent"] = parent_name
            new_area = self.area(
                name=location["name"],
                parent=parent_name,
                uuid=None,
            )
            try:
                self.add(new_area)
            except ValidationError as err:
                self.job.logger.warning(f"Unable to load area {location['name']}. {err}")

    def load_buildings(self, buildings: List[dict]):
        """Load building data from DNAC into DiffSync model.

        Args:
            buildings (List[dict]): List of dictionaries containing location information about a building.
        """
        for location in buildings:
            try:
                self.get(self.building, location["name"])
                self.job.logger.warning(f"Building {location['name']} already loaded so skipping.")
                continue
            except ObjectNotFound:
                if self.job.debug:
                    self.job.logger.info(f"Loading building {location['name']}. {location}")
                address, _ = self.conn.find_address_and_type(info=location["additionalInfo"])
                latitude, longitude = self.conn.find_latitude_and_longitude(info=location["additionalInfo"])
                if location["parentId"] in self.dnac_location_map:
                    _area = self.dnac_location_map[location["parentId"]]
                else:
                    _area = {"name": "Global", "parent": None}
                new_building = self.building(
                    name=location["name"],
                    address=address,
                    area=_area["name"],
                    latitude=latitude[:9].rstrip("0"),
                    longitude=longitude[:7].rstrip("0"),
                    tenant=self.tenant.name if self.tenant else None,
                    uuid=None,
                )
                try:
                    self.add(new_building)
                except ValidationError as err:
                    self.job.logger.warning(f"Unable to load building {location['name']}. {err}")

    def load_floors(self, floors: List[dict]):
        """Load floor data from DNAC into DiffSync model.

        Args:
            floors (List[dict]): List of dictionaries containing location information about a floor.
        """
        for location in floors:
            if self.job.debug:
                self.job.logger.info(f"Loading floor {location['name']}. {location}")
            if location["parentId"] in self.dnac_location_map:
                _building = self.dnac_location_map[location["parentId"]]
            else:
                self.job.logger.warning(f"Parent to {location['name']} can't be found so will be skipped.")
                continue
            floor_name = f"{_building['name']} - {location['name']}"
            try:
                self.get(self.floor, {"name": floor_name, "building": _building["name"]})
                self.job.logger.warning(f"Duplicate Floor {floor_name} attempting to be loaded.")
            except ObjectNotFound:
                new_floor = self.floor(
                    name=floor_name,
                    building=_building["name"],
                    tenant=self.tenant.name if self.tenant else None,
                    uuid=None,
                )
                try:
                    self.add(new_floor)
                    try:
                        parent = self.get(self.building, _building["name"])
                        parent.add_child(new_floor)
                    except ObjectNotFound as err:
                        self.job.logger.warning(
                            f"Unable to find building {_building['name']} for floor {floor_name}. {err}"
                        )
                except ValidationError as err:
                    self.job.logger.warning(f"Unable to load floor {floor_name}. {err}")

    def parse_and_sort_locations(self, locations: List[dict]):
        """Separate locations into areas, buildings, and floors for processing. Also sort by siteHierarchy.

        Args:
            locations (List[dict]): List of Locations (Sites) from DNAC to be separated.

        Returns:
            tuple (List[dict], List[dict], List[dict]): Tuple containing lists of areas, buildings, and floors in DNAC to be processed.
        """
        areas, buildings, floors = [], [], []
        for location in locations:
            if not settings.PLUGINS_CONFIG["nautobot_ssot_dna_center"].get("import_global"):
                if location["name"] == "Global":
                    continue
            for info in location["additionalInfo"]:
                if info["attributes"].get("type") == "building":
                    buildings.append(location)
                    self.dnac_location_map[location["id"]]["loc_type"] = "building"
                    break
                elif info["attributes"].get("type") == "floor":
                    floors.append(location)
                    self.dnac_location_map[location["id"]]["loc_type"] = "floor"
                    break
            else:
                areas.append(location)
            if location.get("parentId") and location["parentId"] in self.dnac_location_map:
                self.dnac_location_map[location["id"]]["parent"] = self.dnac_location_map[location["parentId"]]["name"]
            else:
                self.dnac_location_map[location["id"]]["parent"] = None
        # sort areas by length of siteHierarchy so that parent areas loaded before child areas.
        areas = sorted(areas, key=lambda x: len(x["siteHierarchy"].split("/")))
        return areas, buildings, floors

    def build_dnac_location_map(self, locations: List[dict]):
        """Build out the initial DNAC location map for Location ID to name and type.

        Args:
            locations (List[dict]): List of Locations (Sites) from DNAC.

        Returns:
            dict: Dictionary of Locations mapped with ID to their name and location type.
        """
        location_map = {}
        for loc in locations:
            if not settings.PLUGINS_CONFIG["nautobot_ssot_dna_center"].get("import_global"):
                if loc["name"] == "Global":
                    continue
            location_map[loc["id"]] = {"name": loc["name"], "parent": None, "loc_type": "area"}
        return location_map

    def load_devices(self):
        """Load Device data from DNA Center info DiffSync models."""
        PLUGIN_CFG = settings.PLUGINS_CONFIG["nautobot_ssot_dna_center"]
        devices = self.conn.get_devices()
        for dev in devices:
            platform = "unknown"
            dev_role = "Unknown"
            vendor = "Cisco"
            if not dev.get("hostname"):
                self.job.logger.warning(f"Device {dev['id']} is missing hostname so will be skipped.")
                dev["field_validation"] = {
                    "reason": "Failed due to missing hostname.",
                }
                self.failed_import_devices.append(dev)
                continue
            if PLUGIN_CFG.get("hostname_mapping"):
                dev_role = self.conn.parse_hostname_for_role(
                    hostname_map=PLUGIN_CFG["hostname_mapping"], device_hostname=dev["hostname"]
                )
            if dev_role == "Unknown":
                dev_role = dev["role"]
            if dev["softwareType"] in DNAC_PLATFORM_MAPPER:
                platform = DNAC_PLATFORM_MAPPER[dev["softwareType"]]
            else:
                if not dev.get("softwareType") and dev.get("type") and ("3800" in dev["type"] or "9130" in dev["type"]):
                    platform = "cisco_ios"
                if not dev.get("softwareType") and dev.get("family") and "Meraki" in dev["family"]:
                    if not PLUGIN_CFG.get("import_merakis"):
                        continue
                    platform = "cisco_meraki"
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
                self.job.logger.warning(f"Device {dev['hostname']} is missing building so will not be imported.")
                dev["field_validation"] = {
                    "reason": "Missing building assignment.",
                    "device_details": dev_details,
                    "location_data": loc_data,
                }
                self.failed_import_devices.append(dev)
                continue
            try:
                if self.job.debug:
                    self.job.logger.info(
                        f"Loading device {dev['hostname'] if dev.get('hostname') else dev['id']}. {dev}"
                    )
                device_found = self.get(self.device, dev["hostname"])
                if device_found:
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
                    uuid=None,
                )
                try:
                    self.add(new_dev)
                    self.load_ports(device_id=dev["id"], dev=new_dev, mgmt_addr=dev["managementIpAddress"])
                except ValidationError as err:
                    self.job.logger.warning(f"Unable to load device {dev['hostname']}. {err}")
                    dev["field_validation"] = {
                        "reason": f"Failed validation. {err}",
                        "device_details": dev_details,
                        "location_data": loc_data,
                    }
                    self.failed_import_devices.append(dev)

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
                if found_port:
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
            if ip_found:
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
        if PLUGIN_CFG.get("show_failures"):
            if self.failed_import_devices:
                self.job.logger.warning(
                    f"List of {len(self.failed_import_devices)} devices that were unable to be loaded. {json.dumps(self.failed_import_devices, indent=2)}"
                )
            else:
                self.job.logger.info("There weren't any failed device loads. Congratulations!")
