"""Utility functions for working with DNA Center."""

import logging
import re
from typing import List, Tuple

from dnacentersdk import api
from dnacentersdk.exceptions import dnacentersdkException
from netutils.constants import BASE_INTERFACES

from nautobot_ssot_dna_center.constants import BASE_INTERFACE_MAP

LOGGER = logging.getLogger(__name__)


class DnaCenterClient:
    """Client for handling all interactions with DNA Center."""

    def __init__(
        self, url: str, username: str, password: str, port: int = 443, verify: bool = True
    ):  # pylint: disable=too-many-arguments
        """Initialize instance of client."""
        self.url = url
        self.port = port
        self.base_url = f"{self.url}:{self.port}"
        self.username = username
        self.password = password
        self.verify = verify
        self.conn = None

    def connect(self):  # pylint: disable=inconsistent-return-statements
        """Connect to Cisco DNA Center."""
        try:
            self.conn = api.DNACenterAPI(
                base_url=self.base_url, username=self.username, password=self.password, verify=self.verify
            )
        except dnacentersdkException as err:
            raise dnacentersdkException(f"Unable to connect to DNA Center: {err}") from err

    def get_locations(self):
        """Retrieve all location data from DNA Center.

        Returns:
            list: List of Locations (Sites) from DNAC.
        """
        locations, loc_data, loc_names = [], [], []
        try:
            total_num_sites = self.conn.sites.get_site_count()["response"]
            offset = 1
            while len(loc_data) < total_num_sites:
                loc_data.extend(self.conn.sites.get_site(offset=offset)["response"])
                offset = len(loc_data)
            for _, item in enumerate(loc_data):
                if item["siteNameHierarchy"] not in loc_names:
                    loc_names.append(item["siteNameHierarchy"])
                    locations.append(item)
        except dnacentersdkException as err:
            LOGGER.error("Unable to get site information from DNA Center. %s", err)
        return locations

    @staticmethod
    def find_address_and_type(info: List[dict]):
        """Find Site address and type from additionalInfo dict.

        Args:
            info (List[dict]): Site additionalInfo property from DNA Center.

        Returns:
            tuple: Tuple of Site address and type.
        """
        address = ""
        site_type = ""
        for element in info:
            if element["nameSpace"] == "Location":
                address = element["attributes"]["address"]
                site_type = element["attributes"]["type"]
        return (address, site_type)

    @staticmethod
    def find_latitude_and_longitude(info: List[dict]):
        """Find Site latitude and longitude from additionalInfo dict.

        Args:
            info (List[dict]): Site additionalInfo property from DNA Center.

        Returns:
            tuple: Tuple of Site latitude and longitude.
        """
        latitude = ""
        longitude = ""
        for element in info:
            if element["nameSpace"] == "Location":
                latitude = element["attributes"]["latitude"]
                longitude = element["attributes"]["longitude"]
        return (latitude, longitude)

    def get_devices(self):
        """Retrieve all Device data from DNA Center."""
        dev_list = []
        try:
            total_num_devs = self.conn.devices.get_device_count()["response"]
            while len(dev_list) < total_num_devs:
                dev_list.extend(self.conn.devices.get_device_list(offset=len(dev_list) + 1)["response"])
        except dnacentersdkException as err:
            LOGGER.error("Unable to get device information from DNA Center. %s", err)
        return dev_list

    def get_device_detail(self, dev_id: str):
        """Retrieve all Device data from DNA Center.

        Args:
            dev_id (str): ID of device in DNAC to query for details.

        Returns:
            dict: Details about specified dev_id.
        """
        dev_detail = {}
        try:
            dev_detail = self.conn.devices.get_device_detail(search_by=dev_id, identifier="uuid")["response"]
        except dnacentersdkException as err:
            LOGGER.error("Unable to get device detail information from DNA Center. %s", err)
        return dev_detail

    @staticmethod
    def parse_site_hierarchy(location_map: dict, site_hier: str):
        """Parse siteHierarchyGraphId attribute from get_device_detail response.

        Args:
            location_map (dict): Dictionary mapping location ID to name, parent, and location type.
            site_hier (str): The siteHierarchyGraphId field from the get_device_detail response.

        Returns:
            dict: Dictionary of location hierarchy for a device.
        """
        locations = site_hier.lstrip("/").rstrip("/").split("/")
        loc_data = {
            "areas": [],
            "building": "Unassigned",
            "floor": None,
        }
        for location in locations:
            if location in location_map:
                loc_type = location_map[location]["loc_type"]
                loc_name = location_map[location]["name"]
                if loc_type == "area":
                    loc_data["areas"].append(loc_name)
                if loc_type == "building":
                    loc_data["building"] = loc_name
                if loc_type == "floor":
                    loc_data["floor"] = loc_name
        return loc_data

    def get_port_info(self, device_id: str):
        """Retrieve all interfaces for specified device_id from DNAC.

        Args:
            device_id (str): The ID of the Device that the Ports belong to.

        Returns:
            List[dict]: List of dictionaries of information about Ports on specified device_id.
        """
        ports = []
        try:
            ports = self.conn.devices.get_interface_info_by_id(device_id=device_id)["response"]
        except dnacentersdkException as err:
            LOGGER.error("Unable to get port information from DNA Center. %s", err)
        return ports

    @staticmethod
    def get_port_type(port_info: dict):
        """Determine port type based on portType and portName attributes.

        Args:
            port_info (dict): Dictionary from DNAC with Port data.

        Returns:
            str: String defining the type of port that was found. Will return "other" if unable to determine type.
        """
        if port_info["portType"] == "Ethernet SVI" or port_info["portType"] == "Service Module Interface":
            return "virtual"

        base_port_name = re.match("[a-zA-Z]+", port_info["portName"])
        # normalize interface name for BASE_INTERFACE_MAP
        if base_port_name and BASE_INTERFACES.get(base_port_name.group()):
            base_port_name = BASE_INTERFACES[base_port_name.group()]

        if port_info["portType"] == "Ethernet Port" and base_port_name in BASE_INTERFACE_MAP:
            return BASE_INTERFACE_MAP[base_port_name]
        return "other"

    @staticmethod
    def get_port_status(port_info: dict):
        """Determine port status based on admin and operational status.

        Args:
            port_info (dict): Dictionary containing information about a port from DNAC.
        """
        status = "Active"
        if port_info["status"] == "down" and port_info["adminStatus"] == "DOWN":
            status = "Maintenance"

        if port_info["status"] == "down" and port_info["adminStatus"] == "UP":
            status = "Failed"

        if port_info["status"] == "up" and port_info["adminStatus"] == "DOWN":
            status = "Planned"
        return status

    @staticmethod
    def parse_hostname_for_role(hostname_map: List[Tuple[str, str]], device_hostname: str):
        """Parse device hostname from hostname_map to get Device Role.

        Args:
            hostname_map (List[Tuple[str, str]]): List of tuples containing regex to compare with hostname and associated DeviceRole name.
            device_hostname (str): Hostname of Device to determine role of.

        Returns:
            str: Name of DeviceRole. Defaults to Unknown.
        """
        device_role = "Unknown"
        if hostname_map:
            for entry in hostname_map:
                match = re.match(pattern=entry[0], string=device_hostname)
                if match:
                    device_role = entry[1]
        return device_role

    @staticmethod
    def get_model_name(models: str) -> str:
        """Obtain DeviceType model from a list of models.

        Args:
            models (str): String specifying DeviceType model. Potentially a list of models.

        Returns:
            str: Parsed model name. If list of models, just a single model.
        """
        if "," in models:
            model_list = models.split(", ")
            model_list = list(set(model_list))
            if len(model_list) == 1:
                return model_list[0]
        return models
