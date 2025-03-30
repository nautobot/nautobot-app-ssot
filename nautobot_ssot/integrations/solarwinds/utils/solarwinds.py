"""Utility functions for working with SolarWinds."""

import json
import re
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import requests
import urllib3
from netutils.bandwidth import bits_to_name
from netutils.interface import split_interface
from netutils.ip import is_netmask, netmask_to_cidr
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from nautobot_ssot.integrations.solarwinds.constants import ETH_INTERFACE_NAME_MAP, ETH_INTERFACE_SPEED_MAP


class SolarWindsClient:  # pylint: disable=too-many-public-methods, too-many-instance-attributes
    """Class for handling communication to SolarWinds."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        hostname: str,
        username: str,
        password: str,
        port: int = 17774,
        verify: bool = False,
        session: requests.Session = None,
        **kwargs,
    ):
        """Initialize shared variables for SolarWinds client.

        Args:
            hostname (str): Hostname of the SolarWinds server to connect to
            username (str): Username to authenticate with
            password (str): Password to authenticate with
            port (int, optional): Port on the remote server to connect to (17778=Legacy, 17774=preferred). Defaults to 17774.
            verify (bool, optional): Validate the SSL Certificate when using Requests. Defaults to False.
            session (requests.Session, optional): Customized requests session to use. Defaults to None.
            kwargs (dict): Keyword arguments to catch unspecified keyword arguments.
        """
        self.url = f"{hostname}:{port}/SolarWinds/InformationService/v3/Json/"
        self._session = session or requests.Session()
        self._session.auth = (username, password)
        self._session.headers.update({"Content-Type": "application/json"})
        self._session.verify = verify
        if not verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.job = kwargs.pop("job", None)
        self.batch_size = (
            self.job.integration.extra_config.get("batch_size", 100) if self.job.integration.extra_config else 100
        )

        # Set up retries
        self.timeout = kwargs.pop("timeout", None)
        self.retries = kwargs.pop("retries", None)
        if self.retries is not None:
            retry_strategy = Retry(
                total=self.retries,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=[
                    "HEAD",
                    "GET",
                    "PUT",
                    "DELETE",
                    "OPTIONS",
                    "TRACE",
                    "POST",
                ],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)

    def query(self, query: str, **params):
        """Perform a query against the SolarWinds SWIS API.

        Args:
            query (str): SWQL query to execute
            params (dict, optional): Parameters to pass to the query. Defaults to {}.

        Returns:
            dict: JSON response from the SWIS API
        """
        return self._req("POST", "Query", {"query": query, "parameters": params}).json()

    @staticmethod
    def _json_serial(obj):  # pylint: disable=inconsistent-return-statements
        """JSON serializer for objects not serializable by default json code."""
        if isinstance(obj, datetime):
            serial = obj.isoformat()
            return serial

    def _req(self, method: str, frag: str, data: Optional[dict] = None) -> requests.Response:
        """Perform the actual request to the SolarWinds SWIS API.

        Args:
            method (str): HTTP method to use
            frag (str): URL fragment to append to the base URL
            data (dict, optional): Data payload to include in the request. Defaults to {}.

        Returns:
            requests.Response: Response object from the request
        """
        try:
            resp = self._session.request(
                method,
                self.url + frag,
                data=json.dumps(data, default=self._json_serial),
                timeout=self.timeout,
            )

            # try to extract reason from response when request returns error
            if 400 <= resp.status_code < 600:
                try:
                    resp.reason = json.loads(resp.text)["Message"]
                except json.decoder.JSONDecodeError:
                    pass

            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as err:
            self.job.logger.error(f"An error occurred: {err}")
            # Return an empty response object to avoid breaking the calling code
            return requests.Response()

    def get_filtered_container_ids(self, containers: str) -> Dict[str, int]:
        """Get a list of container IDs from SolarWinds.

        Args:
            containers (str): Comma-separated list of container names to get IDs for.

        Returns:
            Dict[str, int]: Dictionary of container names to IDs.
        """
        container_ids = {}
        for container in [c.strip() for c in containers.split(",")]:
            container_id = self.find_container_id_by_name(container_name=container)
            if container_id != -1:
                container_ids[container] = container_id
            else:
                self.job.logger.error(f"Unable to find container {container}.")
        return container_ids

    def get_container_nodes(
        self,
        container_ids: Dict[str, int],
        custom_property: Optional[str] = None,
        location_name: Optional[str] = None,
    ) -> Dict[str, List[dict]]:
        """Get node IDs for all nodes in specified container ID.

        Args:
            container_ids (Dict[str, int]): Dictionary of container names to their ID.
            custom_property (str): Optional SolarWinds CustomProperty which must be True for Nautobot to pull in.
            location_name (str): Optional location name to override container name, and place ALL devices found here.

        Returns:
            Dict[str, List[dict]]: Dictionary of container names to list of node IDs in that container.
        """
        container_nodes = {}
        for container_name, container_id in container_ids.items():
            location = location_name or container_name
            self.job.logger.debug(f"Gathering container nodes for {container_name} CID: {container_id}.")
            container_nodes[location] = self.recurse_collect_container_nodes(
                current_container_id=container_id, custom_property=custom_property
            )
        return container_nodes

    def get_top_level_containers(self, top_container: str) -> Dict[str, int]:
        """Retrieve all containers from SolarWinds.

        Returns:
            Dict[str, int]: Dictionary of container names to IDs.
        """
        top_container_id = self.find_container_id_by_name(container_name=top_container)
        query = f"SELECT ContainerID, Name, MemberPrimaryID FROM Orion.ContainerMembers WHERE ContainerID = '{top_container_id}'"  # noqa: S608
        results = self.query(query)["results"]
        return {x["Name"]: x["MemberPrimaryID"] for x in results}

    def recurse_collect_container_nodes(self, current_container_id: int, custom_property: Optional[str] = None) -> list:
        """Recursively gather all nodes for specified container ID.

        Args:
            current_container_id (int): Container ID to retrieve nodes for.
            custom_property (str): Optional SolarWinds CustomProperty which must be True for Nautobot to pull in.

        Returns:
            list: List of node IDs in specified container.
        """
        nodes_list = []
        if custom_property:
            query = f"SELECT ContainerID, Name, MemberEntityType, MemberPrimaryID, Nodes.CustomProperties.{custom_property} FROM Orion.ContainerMembers INNER JOIN Orion.Nodes ON Nodes.NodeID = ContainerMembers.MemberPrimaryID WHERE ContainerID = '{current_container_id}'"  # noqa: S608
        else:
            query = f"SELECT ContainerID, Name, MemberEntityType, MemberPrimaryID FROM Orion.ContainerMembers WHERE ContainerID = '{current_container_id}'"  # noqa: S608
        container_members = self.query(query)
        if container_members["results"]:
            for member in container_members["results"]:
                if member["MemberEntityType"] == "Orion.Groups":
                    self.job.logger.debug(f"Exploring container: {member['Name']} CID: {member['MemberPrimaryID']}")
                    nodes_list.extend(self.recurse_collect_container_nodes(member["MemberPrimaryID"], custom_property))
                elif member["MemberEntityType"] == "Orion.Nodes":
                    if not custom_property or member.get(custom_property):
                        nodes_list.append(member)
        return nodes_list

    def find_container_id_by_name(self, container_name: str) -> int:
        """Find container ID by name in SolarWinds.

        Args:
            container_name (str): Name of container to be found.

        Returns:
            int: ID for specified container. Returns -1 if not found.
        """
        query_results = self.query(
            f"SELECT ContainerID FROM Orion.Container WHERE Name = '{container_name}'"  # noqa: S608
        )
        if query_results["results"]:
            return query_results["results"][0]["ContainerID"]
        return -1

    def build_node_details(self, nodes: List[dict]) -> Dict[int, dict]:
        """Build dictionary of node information.

        Args:
            nodes (List[dict]): List of node information dictionaries.

        Returns:
            Dict[int, dict]: Dictionary of node information with key being node primaryID.
        """
        node_details = defaultdict(dict)
        for node in nodes:
            node_details[node["MemberPrimaryID"]] = {"NodeHostname": node["Name"], "NodeID": node["MemberPrimaryID"]}
        self.batch_fill_node_details(node_data=nodes, node_details=node_details, nodes_per_batch=self.batch_size)
        self.get_node_prefix_length(node_data=nodes, node_details=node_details, nodes_per_batch=self.batch_size)
        self.job.logger.info("Loading interface details for nodes.")
        self.gather_interface_data(node_data=nodes, node_details=node_details, nodes_per_batch=self.batch_size)
        self.gather_ipaddress_data(node_data=nodes, node_details=node_details, nodes_per_batch=self.batch_size)
        return node_details

    def batch_fill_node_details(self, node_data: list, node_details: dict, nodes_per_batch: int):
        """Retrieve details from SolarWinds about specified nodes.

        Args:
            node_data (list): List of nodes in containers.
            node_details (dict): Dictionary of node details.
            nodes_per_batch (int): Number of nodes to be processed per batch.
        """
        current_idx = 0
        current_batch = 1
        total_batches = (
            len(node_data) // nodes_per_batch
            if len(node_data) % nodes_per_batch == 0
            else len(node_data) // nodes_per_batch + 1
        )

        while current_idx < len(node_data):
            batch_nodes = node_data[current_idx : current_idx + nodes_per_batch]  # noqa E203
            current_idx += nodes_per_batch
            # Get the node details
            if self.job.debug:
                self.job.logger.debug(f"Processing batch {current_batch} of {total_batches} - Orion.Nodes.")
            details_query = """
                SELECT IOSVersion AS Version,
                o.IPAddress,
                Location AS SNMPLocation,
                o.Vendor,
                MachineType AS DeviceType,
                IOSImage,
                h.Model,
                h.ServiceTag,
                o.NodeID
                FROM Orion.Nodes o LEFT JOIN Orion.HardwareHealth.HardwareInfo h ON o.NodeID = h.NodeID
                WHERE NodeID IN (
            """
            for idx, node in enumerate(batch_nodes):
                details_query += f"'{node['MemberPrimaryID']}'"
                if idx < len(batch_nodes) - 1:
                    details_query += ","
            details_query += ")"
            query_results = self.query(details_query)
            if not query_results["results"]:
                if self.job.debug:
                    self.job.logger.error("Error: No node details found for the batch of nodes")
                continue

            for result in query_results["results"]:
                if result["NodeID"] in node_details:
                    node_id = result["NodeID"]
                    node_details[node_id]["Version"] = result["Version"]
                    node_details[node_id]["IPAddress"] = result["IPAddress"]
                    node_details[node_id]["SNMPLocation"] = result["SNMPLocation"]
                    node_details[node_id]["Vendor"] = result["Vendor"]
                    if "aruba" in result["Vendor"].lower():
                        node_details[node_id]["DeviceType"] = result["IOSImage"].strip("MODEL: ")
                    else:
                        node_details[node_id]["DeviceType"] = result["DeviceType"]
                    node_details[node_id]["Model"] = result["Model"]
                    node_details[node_id]["ServiceTag"] = result["ServiceTag"]
                    # making prefix length default of 32 and will updated to the correct value in subsequent query.
                    node_details[node_id]["PFLength"] = 128 if ":" in result["IPAddress"] else 32
            current_batch += 1

    def get_node_prefix_length(self, node_data: list, node_details: dict, nodes_per_batch: int):
        """Gather node prefix length from IPAM.IPInfo if available.

        Args:
            node_data (list): List of nodes in containers.
            node_details (dict): Dictionary of node details.
            nodes_per_batch (int): Number of nodes to be processed per batch.
        """
        current_idx = 0
        current_batch = 1
        total_batches = (
            len(node_data) // nodes_per_batch
            if len(node_data) % nodes_per_batch == 0
            else len(node_data) // nodes_per_batch + 1
        )

        while current_idx < len(node_data):
            batch_nodes = node_data[current_idx : current_idx + nodes_per_batch]  # noqa E203
            current_idx += nodes_per_batch
            # Get the node details
            if self.job.debug:
                self.job.logger.debug(f"Processing batch {current_batch} of {total_batches} - IPAM.IPInfo.")

            query = "SELECT i.CIDR AS PFLength, o.NodeID FROM Orion.Nodes o JOIN IPAM.IPInfo i ON o.IPAddressGUID = i.IPAddressN WHERE o.NodeID IN ("
            for idx, node in enumerate(batch_nodes):
                query += f"'{node['MemberPrimaryID']}'"
                if idx < len(batch_nodes) - 1:
                    query += ","
            query += ")"
            query_results = self.query(query)
            if not query_results["results"]:
                if self.job.debug:
                    self.job.logger.error("Error: No node details found for the batch of nodes")
                continue

            for result in query_results["results"]:
                if result["NodeID"] in node_details:
                    node_details[result["NodeID"]]["PFLength"] = result["PFLength"]
            current_batch += 1

    def gather_interface_data(self, node_data: list, node_details: dict, nodes_per_batch: int):
        """Retrieve interface details from SolarWinds about specified nodes.

        Args:
            node_data (list): List of nodes in containers.
            node_details (dict): Dictionary of node details.
            nodes_per_batch (int): Number of nodes to be processed per batch.
        """
        current_idx = 0
        current_batch = 1
        while current_idx < len(node_data):
            batch_nodes = node_data[current_idx : current_idx + nodes_per_batch]  # noqa E203
            current_idx += nodes_per_batch
            query = """
                SELECT n.NodeID,
                    sa.StatusName AS Enabled,
                    so.StatusName AS Status,
                    i.Name,
                    i.MAC,
                    i.Speed,
                    i.TypeName,
                    i.MTU
                FROM Orion.Nodes n JOIN Orion.NPM.Interfaces i ON n.NodeID = i.NodeID INNER JOIN Orion.StatusInfo sa ON i.AdminStatus = sa.StatusId INNER JOIN Orion.StatusInfo so ON i.OperStatus = so.StatusId
                WHERE n.NodeID IN (
                """
            for idx, node in enumerate(batch_nodes):
                query += f"'{node['MemberPrimaryID']}'"
                if idx < len(batch_nodes) - 1:
                    query += ","
            query += ")"
            query_results = self.query(query)
            if not query_results["results"]:
                self.job.logger.error("Error: No node details found for the batch of nodes")
                continue

            for result in query_results["results"]:
                if result["NodeID"] in node_details:
                    node_id = result["NodeID"]
                    intf_id = result["Name"]
                    if not node_details[node_id].get("interfaces"):
                        node_details[node_id]["interfaces"] = {}
                    if intf_id not in node_details[node_id]["interfaces"]:
                        node_details[node_id]["interfaces"][intf_id] = {}
                    node_details[node_id]["interfaces"][intf_id]["Name"] = result["Name"]
                    node_details[node_id]["interfaces"][intf_id]["Enabled"] = result["Enabled"]
                    node_details[node_id]["interfaces"][intf_id]["Status"] = result["Status"]
                    node_details[node_id]["interfaces"][intf_id]["TypeName"] = result["TypeName"]
                    node_details[node_id]["interfaces"][intf_id]["Speed"] = result["Speed"]
                    node_details[node_id]["interfaces"][intf_id]["MAC"] = result["MAC"]
                    node_details[node_id]["interfaces"][intf_id]["MTU"] = result["MTU"]
            current_batch += 1

    @staticmethod
    def standardize_device_type(node: dict) -> str:
        """Method of choosing DeviceType from various potential locations and standardizing the result.

        Args:
            node (dict): Node details with DeviceType and Model along with Vendor.

        Returns:
            str: Standardized and sanitized string of DeviceType.
        """
        device_type = ""
        if node.get("Vendor"):
            if node.get("Model"):
                device_type = node["Model"].strip()
            if not device_type.strip() and node.get("DeviceType"):
                device_type = node["DeviceType"].strip()
            if not device_type.strip():
                return ""

            if "Aruba" in node["Vendor"]:
                device_type = device_type.replace("Aruba", "").strip()
            elif "Cisco" in node["Vendor"]:
                device_type = device_type.replace("Cisco", "").strip()
                device_type = device_type.replace("Catalyst ", "C").strip()
                if device_type:
                    if not any(
                        s in device_type.upper() for s in ["WS-", "WLC", "ASR", "WIRELESS"]
                    ) and not device_type.startswith("N"):
                        device_type = f"WS-{device_type}"
            elif "Palo" in node["Vendor"]:
                pass  # Nothing needed yet.
        return device_type

    def determine_interface_type(self, interface: dict) -> str:
        """Determine interface type from a combination of Interface name, speed, and TypeName.

        Args:
            interface (dict): Dictionary of Interface data to use to determine type.

        Returns:
            str: Interface type based upon Interface name, speed, and TypeName.
        """
        intf_default = "virtual"
        if interface.get("TypeName") == "ethernetCsmacd":
            intf_name = split_interface(interface=interface["Name"])[0]
            if intf_name in ETH_INTERFACE_NAME_MAP:
                return ETH_INTERFACE_NAME_MAP[intf_name]
            intf_speed = bits_to_name(int(interface["Speed"]))
            if intf_speed in ETH_INTERFACE_SPEED_MAP:
                return ETH_INTERFACE_SPEED_MAP[intf_speed]
            if intf_name == "Ethernet":
                return ETH_INTERFACE_NAME_MAP["GigabitEthernet"]
            if self.job.debug:
                self.job.logger.debug(f"Unable to find Ethernet interface in map: {intf_name}")
        return intf_default

    @staticmethod
    def extract_version(version: str) -> str:
        """Extract Device software version from string.

        Args:
            version (str): Version string from SolarWinds.

        Returns:
            str: Extracted version string.
        """
        # Match on versions that have paranthesizes in string
        sanitized_version = re.sub(pattern=r",?\s[Copyright,RELEASE].*", repl="", string=version)
        return sanitized_version

    def gather_ipaddress_data(self, node_data: list, node_details: dict, nodes_per_batch: int):
        """Retrieve IPAddress details from SolarWinds about specified nodes.

        Args:
            node_data (list): List of nodes in containers.
            node_details (dict): Dictionary of node details.
            nodes_per_batch (int): Number of nodes to be processed per batch.
        """
        current_idx = 0
        current_batch = 1
        while current_idx < len(node_data):
            batch_nodes = node_data[current_idx : current_idx + nodes_per_batch]  # noqa E203
            current_idx += nodes_per_batch
            query = """
                SELECT NIPA.NodeID,
                    NIPA.InterfaceIndex,
                    NIPA.IPAddress,
                    NIPA.IPAddressType,
                    NPMI.Name,
                    NIPA.SubnetMask
                    FROM Orion.NodeIPAddresses NIPA INNER JOIN Orion.NPM.Interfaces NPMI ON NIPA.NodeID=NPMI.NodeID AND NIPA.InterfaceIndex=NPMI.InterfaceIndex INNER JOIN Orion.Nodes N ON NIPA.NodeID=N.NodeID
                    WHERE NIPA.NodeID IN (
                """
            for idx, node in enumerate(batch_nodes):
                query += f"'{node['MemberPrimaryID']}'"
                if idx < len(batch_nodes) - 1:
                    query += ","
            query += ")"
            query_results = self.query(query)
            if not query_results["results"]:
                self.job.logger.error("Error: No node details found for the batch of nodes")
                continue

            for result in query_results["results"]:
                if result["NodeID"] in node_details:
                    node_id = result["NodeID"]
                    ip_id = result["IPAddress"]
                    if is_netmask(result["SubnetMask"]):
                        netmask_cidr = netmask_to_cidr(netmask=result["SubnetMask"])
                    else:
                        if ":" in result["IPAddress"]:
                            netmask_cidr = 128
                        else:
                            netmask_cidr = 32
                    if not node_details[node_id].get("ipaddrs"):
                        node_details[node_id]["ipaddrs"] = {}
                    if ip_id not in node_details[node_id]["ipaddrs"]:
                        node_details[node_id]["ipaddrs"][ip_id] = {}
                    node_details[node_id]["ipaddrs"][ip_id]["IPAddress"] = result["IPAddress"]
                    node_details[node_id]["ipaddrs"][ip_id]["SubnetMask"] = netmask_cidr
                    node_details[node_id]["ipaddrs"][ip_id]["IPAddressType"] = result["IPAddressType"]
                    node_details[node_id]["ipaddrs"][ip_id]["IntfName"] = result["Name"]
            current_batch += 1


def determine_role_from_devicetype(device_type: str, role_map: dict) -> str:
    """Determine Device Role from passed DeviceType.

    Args:
        device_type (str): DeviceType model to determine Device Role.
        role_map (dict): Dictionary mapping DeviceType model to Device Role name.

    Returns:
        str: Device Role name if match found else blank string.
    """
    role = ""
    if device_type in role_map:
        return role_map[device_type]
    return role


def determine_role_from_hostname(hostname: str, role_map: dict) -> str:
    """Determine Device Role from passed Hostname.

    Args:
        hostname (str): Device hostname to determine Device Role.
        role_map (dict): Dictionary mapping regex patterns for Device hostnames to Device Role name.

    Returns:
        str: Device Role name if match found else blank string.
    """
    role = ""
    for pattern, role_name in role_map.items():
        if re.match(pattern, hostname):
            return role_name
    return role
