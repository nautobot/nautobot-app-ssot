"""Utility functions for Device42 API."""

import re
from typing import List

import requests
import urllib3
from diffsync.exceptions import ObjectNotFound
from nautobot.core.settings_funcs import is_truthy
from netutils.lib_mapper import PYATS_LIB_MAPPER

from nautobot_ssot.integrations.device42.constant import DEFAULTS, FC_INTF_MAP, INTF_NAME_MAP, PHY_INTF_MAP, PLUGIN_CFG
from nautobot_ssot.integrations.device42.diffsync.models.base.ipam import VLAN


class MissingConfigSetting(Exception):
    """Exception raised for missing configuration settings.

    Attributes:
        message (str): Returned explanation of Error.
    """

    def __init__(self, setting):
        """Initialize Exception with Setting that is missing and message."""
        self.setting = setting
        self.message = f"Missing configuration setting - {setting}!"
        super().__init__(self.message)


def merge_offset_dicts(orig_dict: dict, offset_dict: dict) -> dict:
    """Method to merge two dicts and merge a list if found.

    Args:
        orig_dict (dict): Dict to have data merged from.
        offset_dict (dict): Dict to be merged into with offset data. Expects this to be like orig_dict but with offset data.

    Returns:
        dict: Dict with merged data from both dicts.
    """
    out = {}
    for key, value in offset_dict.items():
        if key in orig_dict and key in offset_dict:
            if isinstance(value, list):
                out[key] = orig_dict[key] + value
            else:
                out[key] = value
    return out


def get_intf_type(intf_record: dict) -> str:  # pylint: disable=too-many-branches
    """Method to determine an Interface type based on a few factors.

    Those factors include:
        - Port type
        - Port Speed Note: `port_speed` was used instead of `speedcapable` as `speedcapable` reported nothing.
        - Discovered type for port

    Anything explicitly not matched will go to `other`.

    Args:
        intf_record (dict): Interface record from Device42 with details about the Port.

    Returns:
        _port_type (str): The Nautobot type appropriate for the interface based upon criteria explained above.
    """
    _port_name = re.search(r"^[a-zA-Z]+-?[a-zA-Z]+", intf_record["port_name"].strip())

    if _port_name:
        _port_name = _port_name.group()

    _port_type = "other"
    # if switch is physical and name is from PHY_INTF_MAP dict
    if intf_record["port_type"] == "physical" and intf_record.get("discovered_type"):
        if (
            "ethernet" in intf_record["discovered_type"]
            and intf_record.get("port_speed")
            and intf_record["port_speed"] in PHY_INTF_MAP
        ):
            _port_type = PHY_INTF_MAP[intf_record["port_speed"]]
        elif (
            "fibreChannel" in intf_record["discovered_type"]
            and intf_record.get("port_speed")
            and intf_record["port_speed"] in FC_INTF_MAP
        ):
            _port_type = FC_INTF_MAP[intf_record["port_speed"]]
        elif intf_record["port_speed"] in PHY_INTF_MAP:
            _port_type = PHY_INTF_MAP[intf_record["port_speed"]]
        elif _port_name and _port_name in INTF_NAME_MAP:
            _port_type = INTF_NAME_MAP[_port_name]["itype"]
        elif "gigabitEthernet" in intf_record["discovered_type"]:
            _port_type = "1000base-t"
        elif "dot11" in intf_record["discovered_type"]:
            _port_type = "ieee802.11a"
    if intf_record["port_type"] == "logical" and intf_record.get("discovered_type"):
        if intf_record["discovered_type"] == "ieee8023adLag" or intf_record["discovered_type"] == "lacp":
            _port_type = "lag"
        elif (
            intf_record["discovered_type"] == "softwareLoopback"
            or intf_record["discovered_type"] == "l2vlan"
            or intf_record["discovered_type"] == "propVirtual"
        ):
            if _port_name and re.search(r"[pP]ort-?[cC]hannel", _port_name):
                _port_type = "lag"
            else:
                _port_type = "virtual"
    return _port_type


def get_intf_status(port: dict):
    """Method to determine Interface Status.

    Args:
        port (dict): Dictionary containing port `up` and `up_admin` keys.
    """
    _status = "Planned"
    if "up" in port and "up_admin" in port:
        if not is_truthy(port["up"]) and not is_truthy(port["up_admin"]):
            _status = "Decommissioning"
        elif not is_truthy(port["up"]) and is_truthy(port["up_admin"]):
            _status = "Failed"
        elif is_truthy(port["up"]) and is_truthy(port["up_admin"]):
            _status = "Active"
    elif port.get("up_admin"):
        _status = "Active"
    return _status


def get_netmiko_platform(network_os: str) -> str:
    """Method to return the netmiko platform if a pyATS platform is provided.

    Args:
        network_os (str): Name of platform to map if match found.

    Returns:
        str: Netmiko platform name or original if no match.
    """
    if network_os:
        if network_os == "f5":
            network_os = "bigip"
        net_os = network_os.replace("-", "")
        if net_os in PYATS_LIB_MAPPER:
            return PYATS_LIB_MAPPER[net_os]
    return network_os


def find_device_role_from_tags(tag_list: List[str]) -> str:
    """Determine a Device role based upon a Tag matching the `role_prepend` setting.

    Args:
        tag_list (List[str]): List of Tags as strings to search.

    Returns:
        str: The Default device role defined in app settings.
    """
    _prepend = PLUGIN_CFG.get("device42_role_prepend")
    if _prepend:
        for _tag in tag_list:
            if re.search(_prepend, _tag):
                return re.sub(_prepend, "", _tag)
    return DEFAULTS.get("device_role")


def get_facility(tags: List[str]):  # pylint: disable=inconsistent-return-statements
    """Determine Site facility from a specified Tag."""
    if PLUGIN_CFG.get("device42_facility_prepend"):
        for _tag in tags:
            if re.search(PLUGIN_CFG.get("device42_facility_prepend"), _tag):
                return re.sub(PLUGIN_CFG.get("device42_facility_prepend"), "", _tag)


def get_custom_field_dict(cfields: List[dict]) -> dict:
    """Creates dictionary of CustomField with CF key, value, and description.

    Args:
        cfields (List[dict]): List of Custom Fields with their value and notes.

    Returns:
        cf_dict (dict): Return a dict of CustomField with key, value, and note (description).
    """
    cf_dict = {}
    for cfield in cfields:
        cf_dict[cfield["key"]] = cfield
    return cf_dict


def load_vlan(  # pylint: disable=dangerous-default-value, too-many-arguments
    diffsync,
    vlan_id: int,
    site_name: str,
    vlan_name: str = "",
    description: str = "",
    custom_fields: dict = {},
    tags: list = [],
):
    """Find or create specified Site VLAN.

    Args:
        diffsync (Device42Adapter): Device42Adapter with logger and get method.
        vlan_id (int): VLAN ID for site.
        site_name (str): Site name for associated VLAN.
        vlan_name (str): Name of VLAN to be created.
        description (str): Description for VLAN.
        custom_fields (dict): Dictionary of CustomFields for VLAN.
        tags (list): List of Tags to be applied to VLAN.
    """
    try:
        diffsync.get(VLAN, {"vlan_id": vlan_id, "building": site_name})
        diffsync.job.logger.warning(f"Duplicate VLAN attempted to be loaded: {vlan_id} {site_name}")
    except ObjectNotFound:
        diffsync.job.logger.info(f"Loading VLAN {vlan_id} {vlan_name} for {site_name}")
        new_vlan = VLAN(
            name=f"VLAN{vlan_id:04d}" if not vlan_name else vlan_name,
            vlan_id=vlan_id,
            description=description,
            building=site_name,
            custom_fields=custom_fields,
            tags=tags,
            uuid=None,
        )
        diffsync.add(new_vlan)


class Device42API:  # pylint: disable=too-many-public-methods
    """Device42 API class."""

    def __init__(self, base_url: str, username: str, password: str, verify: bool = True):
        """Create Device42 API connection."""
        self.base_url = base_url
        self.verify = verify
        self.username = username
        self.password = password
        self.headers = {"Content-Type": "application/x-www-form-urlencoded"}

        if verify is False:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def validate_url(self, path):
        """Validate URL formatting is correct."""
        if not self.base_url.endswith("/") and not path.startswith("/"):
            full_path = f"{self.base_url}/{path}"
        else:
            full_path = f"{self.base_url}{path}"
        if not full_path.endswith("/"):
            return full_path
        return full_path

    def api_call(self, path: str, method: str = "GET", params: dict = None, payload: dict = None):
        """Method to send Request to Device42 of type `method`. Defaults to GET request.

        Args:
            path (str): API path to send request to.
            method (str, optional): API request method. Defaults to "GET".
            params (dict, optional): Additional parameters to send to API. Defaults to None.
            payload (dict, optional): Message payload to be sent as part of API call.

        Raises:
            Exception: Error thrown if request errors.

        Returns:
            dict: JSON payload of API response.
        """
        url = self.validate_url(path)
        return_data = {}

        if params is None:
            params = {}

        params.update(
            {
                "_paging": "1",
                "_return_as_object": "1",
                "_max_results": "1000",
            }
        )

        resp = requests.request(
            method=method,
            headers=self.headers,
            auth=(self.username, self.password),
            url=url,
            params=params,
            verify=self.verify,
            data=payload,
            timeout=60,
        )
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as err:
            print(f"Error in communicating to Device42 API: {err}")
            return False

        return_data = resp.json()
        # print(f"Total count for {url}: {return_data.get('total_count')}")
        # Handle Device42 pagination
        counter = 0
        pagination = False
        if isinstance(return_data, dict) and return_data.get("total_count"):
            while (return_data.get("offset") + return_data.get("limit")) < return_data.get("total_count"):
                pagination = True
                # print("Handling paginated response from Device42.")
                new_offset = return_data["offset"] + return_data["limit"]
                params.update({"offset": new_offset})
                counter += 1
                response = requests.request(
                    method="GET",
                    headers=self.headers,
                    auth=(self.username, self.password),
                    url=url,
                    params=params,
                    timeout=60,
                    verify=self.verify,
                )
                response.raise_for_status()
                return_data = merge_offset_dicts(return_data, response.json())
                # print(
                #     f"Number of devices: {len(return_data['Devices'])}.\noffset: {return_data.get('offset')}.\nlimit: {return_data.get('limit')}."
                # )

                # Handle possible infinite loop.
                if counter > 10000:
                    print("Too many pagination loops in Device42 request. Possible infinite loop.")
                    print(url)
                    break

            # print(f"Exiting API request loop after {counter} loops.")

        if pagination:
            return_data.pop("offset", None)

        return return_data

    def doql_query(self, query: str) -> dict:
        """Method to perform a DOQL query against Device42.

        Args:
            query (str): DOQL query to be sent to Device42.

        Returns:
            dict: Returned data from Device42 for DOQL query.
        """
        params = {
            "query": query,
            "output_type": "json",
        }
        url = "services/data/v1.0/query/"
        return self.api_call(path=url, params=params)

    def get_buildings(self) -> List:
        """Method to get all Buildings from Device42."""
        return self.api_call(path="api/1.0/buildings")["buildings"]

    def get_building_pks(self) -> dict:
        """Method to obtain all Buildings from Device42 mapped to their PK.

        Returns:
            dict: Dictionary of Buildings with their PK as key.
        """
        query = "SELECT * FROM view_building_v1"
        results = self.doql_query(query=query)
        return {x["building_pk"]: x for x in results}

    def get_rooms(self) -> List:
        """Method to get all Rooms from Device42."""
        return self.api_call(path="api/1.0/rooms")["rooms"]

    def get_room_pks(self) -> dict:
        """Method to obtain all Rooms from Device42 mapped to their PK.

        Returns:
            dict: Dictionary of Rooms with their PK as key.
        """
        query = "SELECT * FROM view_room_v1"
        results = self.doql_query(query=query)
        return {x["room_pk"]: x for x in results}

    def get_racks(self) -> List:
        """Method to get all Racks from Device42."""
        return self.api_call(path="api/1.0/racks")["racks"]

    def get_rack_pks(self) -> dict:
        """Method to obtain all Racks from Device42 mapped to their PK.

        Returns:
            dict: Dictionary of Racks with their PK as key.
        """
        query = "SELECT * FROM view_rack_v1"
        results = self.doql_query(query=query)
        return {x["rack_pk"]: x for x in results}

    def get_vendors(self) -> List:
        """Method to get all Vendors from Device42."""
        return self.api_call(path="api/1.0/vendors")["vendors"]

    def get_hardware_models(self) -> List:
        """Method to get all Hardware Models from Device42."""
        return self.api_call(path="api/1.0/hardwares")["models"]

    def get_devices(self) -> List[dict]:
        """Method to get all Network Devices from Device42."""
        return self.api_call(path="api/1.0/devices/all/?is_it_switch=yes")["Devices"]

    def get_cluster_members(self) -> dict:
        """Method to get all member devices of a cluster from Device42.

        Returns:
            dict: Dictionary of all clusters with associated members.
        """
        query = "SELECT m.name as cluster, string_agg(d.name, '%3B ') as members, h.name as hardware, d.network_device, d.os_name as os, b.name as customer, d.tags FROM view_device_v1 m JOIN view_devices_in_cluster_v1 c ON c.parent_device_fk = m.device_pk JOIN view_device_v1 d ON d.device_pk = c.child_device_fk JOIN view_hardware_v1 h ON h.hardware_pk = d.hardware_fk JOIN view_customer_v1 b ON b.customer_pk = d.customer_fk WHERE m.type like '%cluster%' GROUP BY m.name, h.name, d.network_device, d.os_name, b.name, d.tags"
        _results = self.doql_query(query=query)

        return {
            _i["cluster"]: {
                "members": sorted(list(_i["members"].split("%3B "))),
                "is_network": _i["network_device"],
                "hardware": _i["hardware"],
                "os": _i["os"],
                "customer": _i["customer"],
                "tags": _i["tags"].split(",") if _i.get("tags") else [],
            }
            for _i in _results
        }

    def get_ports_with_vlans(self) -> List[dict]:
        """Method to get all Ports with attached VLANs from Device42.

        This retrieves only the information we care about via DOQL in one giant json blob instead of multiple API calls.

        Returns:
            List[dict]: Dict of interface information from DOQL query.
        """
        query = "SELECT array_agg( distinct concat (v.vlan_pk)) AS vlan_pks, n.netport_pk, n.port AS port_name, n.description, n.up, n.up_admin, n.discovered_type, n.hwaddress, n.port_type, n.port_speed, n.mtu, n.tags, n.second_device_fk, d.name AS device_name FROM view_vlan_v1 v LEFT JOIN view_vlan_on_netport_v1 vn ON vn.vlan_fk = v.vlan_pk LEFT JOIN view_netport_v1 n ON n.netport_pk = vn.netport_fk LEFT JOIN view_device_v1 d ON d.device_pk = n.device_fk WHERE n.port is not null GROUP BY n.netport_pk, n.port, n.description, n.up, n.up_admin, n.discovered_type, n.hwaddress, n.port_type, n.port_speed, n.mtu, n.tags, n.second_device_fk, d.name"
        return self.doql_query(query=query)

    def get_ports_wo_vlans(self) -> List[dict]:
        """Method to get all Ports from Device42.

        Returns:
            List[dict]: Dict of Interface information from DOQL query.
        """
        query = "SELECT m.netport_pk, m.port as port_name, m.description, m.up_admin, m.discovered_type, m.hwaddress, m.port_type, m.port_speed, m.mtu, m.tags, m.second_device_fk, d.name as device_name FROM view_netport_v1 m JOIN view_device_v1 d on d.device_pk = m.device_fk WHERE m.port is not null GROUP BY m.netport_pk, m.port, m.description, m.up_admin, m.discovered_type, m.hwaddress, m.port_type, m.port_speed, m.mtu, m.tags, m.second_device_fk, d.name"
        return self.doql_query(query=query)

    def get_port_default_custom_fields(self) -> List[dict]:
        """Method to retrieve the default CustomFields for Ports from Device42.

        This is needed to ensure all Posts have same CustomFields to match Nautobot.

        Returns:
            List[dict]: List of dictionaries of CustomFields matching D42 format from the API without values.
        """
        query = "SELECT cf.key, cf.value, cf.notes FROM view_netport_custom_fields_v1 cf"
        results = self.doql_query(query=query)
        return self.get_all_custom_fields(results)

    def get_port_custom_fields(self) -> dict:
        """Method to retrieve custom fields for Ports from Device42.

        Returns:
            dict: Dictionary of CustomFields matching D42 format from the API.
        """
        query = "SELECT cf.key, cf.value, cf.notes, np.port as port_name, d.name as device_name FROM view_netport_custom_fields_v1 cf LEFT JOIN view_netport_v1 np ON np.netport_pk = cf.netport_fk LEFT JOIN view_device_v1 d ON d.device_pk = np.device_fk"
        results = self.doql_query(query=query)
        _fields = {}
        for _cf in results:
            _fields[_cf["device_name"]] = {}
        for _cf in results:
            _fields[_cf["device_name"]][_cf["port_name"]] = {}
        for _cf in results:
            _fields[_cf["device_name"]][_cf["port_name"]][_cf["key"]] = {
                "key": _cf["key"],
                "value": _cf["value"],
                "notes": _cf["notes"],
            }
        return _fields

    def get_vrfgroups(self) -> dict:
        """Method to retrieve VRF Groups from Device42.

        Returns:
            dict: Response from Device42 containing VRFGroups.
        """
        return self.api_call(path="api/1.0/vrfgroup/")["vrfgroup"]

    def get_subnets(self) -> List[dict]:
        """Method to get all subnets and associated data from Device42.

        Returns:
            dict: Dict of subnets from Device42.
        """
        query = "SELECT s.name, s.network, s.mask_bits, s.tags, v.name as vrf FROM view_subnet_v1 s JOIN view_vrfgroup_v1 v ON s.vrfgroup_fk = v.vrfgroup_pk"
        return self.doql_query(query=query)

    def get_subnet_default_custom_fields(self) -> dict:
        """Method to retrieve the default CustomFields for Subnets from Device42.

        This is needed to ensure all Subnets have same CustomFields to match Nautobot.

        Returns:
            dict: Dictionary of CustomFields matching D42 format from the API without values.
        """
        query = "SELECT cf.key, cf.value, cf.notes FROM view_subnet_custom_fields_v1 cf"
        results = self.doql_query(query=query)
        return self.get_all_custom_fields(results)

    def get_subnet_custom_fields(self) -> dict:
        """Method to retrieve custom fields for Subnets from Device42.

        Returns:
            dict: Dictionary of dictionaries of CustomFields matching D42 format from the API.
        """
        query = "SELECT cf.key, cf.value, cf.notes, s.name AS subnet_name, s.network, s.mask_bits FROM view_subnet_custom_fields_v1 cf LEFT JOIN view_subnet_v1 s ON s.subnet_pk = cf.subnet_fk"
        results = self.doql_query(query=query)

        default_cfs = self.get_subnet_default_custom_fields()

        _fields = {}
        for _cf in results:
            _fields[f"{_cf['network']}/{_cf['mask_bits']}"] = default_cfs

        for _cf in results:
            _fields[f"{_cf['network']}/{_cf['mask_bits']}"][_cf["key"]] = {
                "key": _cf["key"],
                "value": _cf["value"],
                "notes": _cf["notes"],
            }
        return _fields

    def get_ip_addrs(self) -> List[dict]:
        """Method to get all IP addresses and relevant data from Device42 via DOQL.

        Returns:
            List[dict]: List of dicts with info about each IP address.
        """
        query = "SELECT i.ip_address, i.available, i.label, i.tags, np.netport_pk, s.network as subnet, s.mask_bits as netmask, v.name as vrf FROM view_ipaddress_v1 i LEFT JOIN view_subnet_v1 s ON s.subnet_pk = i.subnet_fk LEFT JOIN view_netport_v1 np ON np.netport_pk = i.netport_fk LEFT JOIN view_vrfgroup_v1 v ON v.vrfgroup_pk = s.vrfgroup_fk WHERE s.mask_bits <> 0"
        return self.doql_query(query=query)

    def get_ipaddr_default_custom_fields(self) -> dict:
        """Method to retrieve the default CustomFields for IP Addresses from Device42.

        This is needed to ensure all IPAddresses have same CustomFields to match Nautobot.

        Returns:
            dict: Dictionary of CustomFields with label as key and remaining info as value.
        """
        query = "SELECT cf.key, cf.value, cf.notes FROM view_ipaddress_custom_fields_v1 cf"
        results = self.doql_query(query=query)
        return self.get_all_custom_fields(results)

    def get_ipaddr_custom_fields(self) -> dict:
        """Method to retrieve the CustomFields for IP Addresses from Device42.

        Returns:
            dict: Dictionary of CustomFields from D42 matched to IP Addressmatching D42 format from the API with values.
        """
        query = "SELECT cf.key, cf.value, cf.notes, i.ip_address, s.mask_bits FROM view_ipaddress_custom_fields_v1 cf LEFT JOIN view_ipaddress_v1 i ON i.ipaddress_pk = cf.ipaddress_fk LEFT JOIN view_subnet_v1 s ON s.subnet_pk = i.subnet_fk"
        results = self.doql_query(query=query)

        default_cfs = self.get_all_custom_fields(results)

        _fields = {}
        for _cf in results:
            addr = f"{_cf['ip_address']}/{_cf['mask_bits']}"
            if addr not in _fields:
                _fields[addr] = default_cfs
            _fields[addr][_cf["key"]] = {
                "key": _cf["key"],
                "value": _cf["value"],
                "notes": _cf["notes"],
            }
        return _fields

    @staticmethod
    def get_all_custom_fields(custom_fields: List[dict]) -> dict:
        """Get all Custom Fields for object.

        As Device42 only returns CustomFields with values in them when using DOQL, we need to compile a list of all Custom Fields on an object to match Nautobot method.

        Args:
            custom_fields (List[dict]): List of Custom Fields for an object.

        Returns:
            dict: List of all Custom Fields nulled.
        """
        _cfs = {}
        for _cf in custom_fields:
            _cfs[_cf["key"]] = {
                "key": _cf["key"],
                "value": None,
                "notes": None,
            }
        return _cfs

    def get_vlans_with_location(self) -> List[dict]:
        """Method to get all VLANs with Building and Customer info to attach to find Site.

        Returns:
            List[dict]: List of dicts of VLANs and location information.
        """
        query = "SELECT v.vlan_pk, v.number AS vid, v.description, v.tags, vn.vlan_name, b.name as building, c.name as customer FROM view_vlan_v1 v LEFT JOIN view_vlan_on_netport_v1 vn ON vn.vlan_fk = v.vlan_pk LEFT JOIN view_netport_v1 n on n.netport_pk = vn.netport_fk LEFT JOIN view_device_v2 d on d.device_pk = n.device_fk LEFT JOIN view_building_v1 b ON b.building_pk = d.building_fk LEFT JOIN view_customer_v1 c ON c.customer_pk = d.customer_fk WHERE vn.vlan_name is not null and v.number <> 0 GROUP BY v.vlan_pk, v.number, v.description, v.tags, vn.vlan_name, b.name, c.name"
        return self.doql_query(query=query)

    def get_vlan_info(self) -> dict:
        """Method to obtain the VLAN name and ID paired to primary key.

        Returns:
            dict: Mapping of VLAN primary key to VLAN name and ID.
        """
        vinfo_query = "SELECT v.vlan_pk, v.name, v.number as vid FROM view_vlan_v1 v"
        cfields_query = "SELECT cf.key, cf.value, cf.notes, v.vlan_pk FROM view_vlan_custom_fields_v1 cf LEFT JOIN view_vlan_v1 v ON v.vlan_pk = cf.vlan_fk"
        doql_vlans = self.doql_query(query=vinfo_query)
        vlans_cfs = self.doql_query(query=cfields_query)
        vlan_dict = {str(x["vlan_pk"]): {"name": x["name"], "vid": x["vid"]} for x in doql_vlans}
        for _cf in vlans_cfs:
            if str(_cf["vlan_pk"]) in vlan_dict:
                vlan_dict[str(_cf["vlan_pk"])]["custom_fields"] = {}
        for _cf in vlans_cfs:
            vlan_dict[str(_cf["vlan_pk"])]["custom_fields"][_cf["key"]] = {
                "key": _cf["key"],
                "value": _cf["value"],
                "notes": _cf["notes"],
            }
        return vlan_dict

    def get_device_pks(self) -> dict:
        """Get all Devices with their primary keys for reference in other functions.

        Returns:
            dict: Dict of Devices where the key is the primary key of the Device.
        """
        query = "SELECT name, device_pk FROM view_device_v1 WHERE name <> ''"
        _devs = self.doql_query(query=query)
        return {x["device_pk"]: x for x in _devs}

    def get_port_pks(self) -> dict:
        """Get all ports with their associated primary keys for reference in other functions.

        Returns:
            dict: Dict of ports where key is the primary key of the Port with the port name.
        """
        query = "SELECT np.port, np.netport_pk, np.hwaddress, np.second_device_fk, d.name as device FROM view_netport_v1 np JOIN view_device_v1 d ON d.device_pk = np.device_fk"
        _ports = self.doql_query(query=query)
        for _port in _ports:
            if not _port["port"] and _port.get("hwaddress"):
                _port["port"] = _port["hwaddress"]
        return {x["netport_pk"]: x for x in _ports}

    def get_port_connections(self) -> dict:
        """Gather all Ports with connections to determine connections between interfaces for Cables.

        Returns:
            dict: Information about each port and it's connection information.
        """
        query = "SELECT netport_pk as src_port, device_fk as src_device, second_device_fk as second_src_device, remote_netport_fk as dst_port FROM view_netport_v1 WHERE device_fk is not null AND remote_netport_fk is not null"
        return self.doql_query(query=query)

    def get_telcocircuits(self) -> List[dict]:
        """Method to retrieve all information about TelcoCircuits from Device42.

        Returns:
            List[dict]: List of dictionaries containing information about each circuit in Device42.
        """
        query = "SELECT * FROM view_telcocircuit_v1"
        return self.doql_query(query=query)

    def get_vendor_pks(self) -> dict:
        """Method to obtain all Vendors from Device42 mapped to their PK.

        Returns:
            dict: Dictionary of Vendors with their PK as key.
        """
        query = "SELECT * FROM view_vendor_v1"
        results = self.doql_query(query=query)
        return {x["vendor_pk"]: x for x in results}

    def get_patch_panels(self) -> List[dict]:
        """Method to obtain all patch panels from Device42.

        Returns:
            dict: Dictionary of Patch Panels in Device42.
        """
        query = "SELECT a.name, a.in_service, a.serial_no, a.customer_fk, a.building_fk, a.calculated_building_fk, a.room_fk, a.calculated_room_fk, a.calculated_rack_fk, a.size, a.depth, m.number_of_ports, m.name as model_name, m.port_type_name as port_type, v.name as vendor, a.rack_fk, a.start_at as position, a.orientation FROM view_asset_v1 a LEFT JOIN view_patchpanelmodel_v1 m ON m.patchpanelmodel_pk = a.patchpanelmodel_fk JOIN view_vendor_v1 v ON v.vendor_pk = m.vendor_fk WHERE a.patchpanelmodel_fk is not null AND a.name is not null"
        return self.doql_query(query=query)

    def get_patch_panel_port_pks(self) -> dict:
        """Method to obtain all Patch Panel Ports from Device42 mapped to their PK.

        Returns:
            dict: Dictionary of Patch Panel Ports with their PK as key.
        """
        query = "SELECT p.*, a.name FROM view_patchpanelport_v1 p JOIN view_asset_v1 a ON a.asset_pk = p.patchpanel_asset_fk"
        results = self.doql_query(query=query)
        return {x["patchpanelport_pk"]: x for x in results}

    def get_customer_pks(self) -> dict:
        """Method to obtain all Customers from Device42 mapped to their PK.

        Returns:
            dict: Dictionary of Customers with their PK as key.
        """
        query = "SELECT * FROM view_customer_v1"
        results = self.doql_query(query=query)
        return {x["customer_pk"]: x for x in results}
