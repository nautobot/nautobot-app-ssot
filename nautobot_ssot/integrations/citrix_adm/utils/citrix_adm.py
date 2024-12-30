"""Utility functions for working with Citrix ADM."""

import re
from typing import List, Optional, Union

import requests
import urllib3
from netutils.ip import ipaddress_interface, is_ip_within, netmask_to_cidr


# based on client found at https://github.com/slauger/python-nitro
class CitrixNitroClient:
    """Client for interacting with Citrix ADM NITRO API."""

    def __init__(  # pylint: disable=too-many-arguments
        self, base_url: str, user: str, password: str, job, verify: bool = True
    ):
        """Initialize NITRO client.

        Args:
            base_url (str): Base URL for MAS/ADM API. Must include schema, http(s).
            user (str): Username to authenticate with Citrix ADM.
            password (str): Password to authenticate with Citrix ADM.
            verify (bool, optional): Whether to validate SSL certificate on Citrix ADM or not. Defaults to True.
            job (Job): Job logger to notify users of progress.
        """
        if base_url.endswith("/"):
            base_url = base_url.rstrip("/")
        self.url = base_url
        self.username = user
        self.password = password
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.verify = verify
        if self.verify is False:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.job = job

    def login(self):
        """Login to ADM/MAS and set authorization token to enable further communication."""
        url = "config"
        objecttype = "login"
        login = {"login": {"username": self.username, "password": self.password}}
        payload = f"object={login}"
        response = self.request(method="POST", endpoint=url, objecttype=objecttype, data=payload)
        if response:
            session_id = response["login"][0]["sessionid"]
            self.headers["Cookie"] = f"SESSID={session_id}; path=/; SameSite=Lax; secure; HttpOnly"
        else:
            self.job.logger.error("Error while logging into Citrix ADM. Please validate your configuration is correct.")
            raise requests.exceptions.RequestException()

    def logout(self):
        """Best practice to logout when session is complete."""
        url = "config"
        objecttype = "logout"
        logout = {"logout": {"username": self.username, "password": self.password}}
        payload = f"object={logout}"
        self.headers.pop("_MPS_API_PROXY_MANAGED_INSTANCE_IP", None)
        self.headers.pop("_MPS_API_PROXY_MANAGED_INSTANCE_USERNAME", None)
        self.headers.pop("_MPS_API_PROXY_MANAGED_INSTANCE_PASSWORD", None)
        self.request(method="POST", endpoint=url, objecttype=objecttype, data=payload)

    def request(  # pylint: disable=too-many-arguments
        self,
        method: str,
        endpoint: str,
        objecttype: str = "",
        objectname: str = "",
        params: Optional[Union[str, dict]] = None,
        data: Optional[str] = None,
    ):
        """Perform request of specified method to endpoint.

        Args:
            method (str): HTTP method to use with request, ie GET, PUT, POST, etc.
            endpoint (str): API endpoint to query.
            objecttype (str, optional): Specific object type to query the API about. Defaults to "".
            objectname (str, optional): Specifc object to query the API about. Defaults to "".
            params (Optional[Union[str, dict]], optional): Additional parameters for the request. Defaults to None.
            data (Optional[str], optional): Addiontal data payload for the request. Defaults to None.

        Returns:
            dict: Dictionary of data about objectname of objecttype with specified parameters if specified.
        """
        url = self.url + "/nitro/v1/" + endpoint + "/" + objecttype

        if objectname:
            url += "/" + objectname

        if params:
            url += "?"

            if isinstance(params, dict):
                for key, value in params.items():
                    url += key + "=" + value
            else:
                url += params

        _result = requests.request(
            method=method,
            url=url,
            data=data,
            headers=self.headers,
            timeout=60,
            verify=self.verify,
        )
        if _result:
            _result.raise_for_status()
            _result = _result.json()
            if _result.get("errorcode") == 0:
                return _result
            self.job.logger.warning(f"Failure with request: {_result['message']}")
        return {}

    def get_sites(self):
        """Gather all sites configured on MAS/ADM instance."""
        if self.job.debug:
            self.job.logger.info("Getting sites from Citrix ADM.")
        endpoint = "config"
        objecttype = "mps_datacenter"
        params = {"attrs": "city,zipcode,type,name,region,country,latitude,longitude,id"}
        result = self.request("GET", endpoint, objecttype, params=params)
        if result:
            return result[objecttype]
        if self.job.debug:
            self.job.logger.error("Error getting sites from Citrix ADM.")
        return {}

    def get_devices(self):
        """Gather all devices registered to MAS/ADM instance."""
        if self.job.debug:
            self.job.logger.info("Getting devices from Citrix ADM.")
        endpoint = "config"
        objecttype = "managed_device"
        params = {
            "attrs": "ip_address,hostname,gateway,mgmt_ip_address,description,serialnumber,type,display_name,netmask,datacenter_id,version,instance_state,ha_ip_address"
        }
        result = self.request("GET", endpoint, objecttype, params=params)
        if result:
            return result[objecttype]
        self.job.logger.error("Error getting devices from Citrix ADM.")
        return {}

    def get_nsip(self, adc):
        """Gather all nsip addresses from ADC instance using ADM as proxy."""
        endpoint = "config"
        objecttype = "nsip"
        params = {}
        self.headers["_MPS_API_PROXY_MANAGED_INSTANCE_USERNAME"] = self.username
        self.headers["_MPS_API_PROXY_MANAGED_INSTANCE_PASSWORD"] = self.password
        self.headers["_MPS_API_PROXY_MANAGED_INSTANCE_IP"] = adc["ip_address"]
        result = self.request("GET", endpoint, objecttype, params=params)
        if result:
            return result[objecttype]
        if self.job.debug:
            self.job.logger.error(f"Error getting nsip from {adc['hostname']}")
        return {}

    def get_nsip6(self, adc):
        """Gather all nsip6 addresses from ADC instance using ADM as proxy."""
        endpoint = "config"
        objecttype = "nsip6"
        params = {}
        self.headers["_MPS_API_PROXY_MANAGED_INSTANCE_USERNAME"] = self.username
        self.headers["_MPS_API_PROXY_MANAGED_INSTANCE_PASSWORD"] = self.password
        self.headers["_MPS_API_PROXY_MANAGED_INSTANCE_IP"] = adc["ip_address"]
        result = self.request("GET", endpoint, objecttype, params=params)
        if result:
            return result[objecttype]
        if self.job.debug:
            self.job.logger.error(f"Error getting nsip6 from {adc['hostname']}")
        return {}

    def get_vlan_bindings(self, adc):
        """Gather all interface vlan and nsip bindings from ADC instance using ADM as proxy."""
        endpoint = "config"
        objecttype = "vlan_binding"
        params = {"bulkbindings": "yes"}
        self.headers["_MPS_API_PROXY_MANAGED_INSTANCE_USERNAME"] = self.username
        self.headers["_MPS_API_PROXY_MANAGED_INSTANCE_PASSWORD"] = self.password
        self.headers["_MPS_API_PROXY_MANAGED_INSTANCE_IP"] = adc["ip_address"]
        result = self.request("GET", endpoint, objecttype, params=params)
        if result:
            return result[objecttype]
        if self.job.debug:
            self.job.logger.error(f"Error getting vlan bindings from {adc['hostname']}")
        return {}


def parse_version(version: str):
    """Parse Device version from string.

    Args:
        version (str): Version string from device API query.
    """
    result = ""
    match_pattern = r"NetScaler\s(?P<version>NS\d+\.\d+: Build\s\d+\.\d+\.\w+)"
    match = re.match(pattern=match_pattern, string=version)
    if match:
        result = match.group("version")
    return result


def parse_vlan_bindings(vlan_bindings: List[dict], adc: dict, job) -> List[dict]:
    """Parse VLAN Bindings from ADC."""
    ports = []
    for binding in vlan_bindings:
        if binding.get("vlan_interface_binding"):
            if binding.get("vlan_nsip_binding"):
                for nsip in binding["vlan_nsip_binding"]:
                    vlan = nsip["id"]
                    ipaddress = nsip["ipaddress"]
                    netmask = netmask_to_cidr(nsip["netmask"])
                    port = binding["vlan_interface_binding"][0]["ifnum"]
                    record = {"vlan": vlan, "ipaddress": ipaddress, "netmask": netmask, "port": port, "version": 4}
                    ports.append(record)
            if binding.get("vlan_nsip6_binding"):
                for nsip6 in binding["vlan_nsip6_binding"]:
                    vlan = nsip6["id"]
                    ipaddress, netmask = nsip6["ipaddress"].split("/")
                    port = binding["vlan_interface_binding"][0]["ifnum"]
                    record = {"vlan": vlan, "ipaddress": ipaddress, "netmask": netmask, "port": port, "version": 6}
                    ports.append(record)
        else:
            if job.debug:
                job.logger.warning(f"{adc['hostname']}: VLAN {binding['id']} has no interface binding: {binding}.")

    # Account for NSIP in VLAN 1 which is not returned by get_vlan_bindings()
    if vlan_bindings:
        ports_dict = {port["ipaddress"]: port for port in ports}
        if adc["ip_address"] not in ports_dict:
            port = vlan_bindings[0]["vlan_interface_binding"][0]["ifnum"]
            netmask = netmask_to_cidr(adc["netmask"])
            ipaddress = adc["ip_address"]
            record = {"vlan": "1", "ipaddress": ipaddress, "netmask": netmask, "port": port, "version": 4}
            ports.append(record)

            if job.debug:
                job.logger.warning(f"{adc['hostname']} is using VLAN 1 for NSIP.")

    return ports


def parse_nsips(nsips: List[dict], ports: List[dict], adc: dict) -> List[dict]:
    """Parse Netscaler IPv4 Addresses."""
    for nsip in nsips:
        for port in ports:
            if port["ipaddress"] == nsip["ipaddress"]:
                if nsip["type"] == "NSIP":
                    port["tags"] = ["NSIP"]
                break

            if nsip["type"] in ["SNIP", "MIP"] and port["version"] != 6:
                network = str(ipaddress_interface(f"{port['ipaddress']}/{port['netmask']}", "network"))
                if is_ip_within(nsip["ipaddress"], network):
                    _tags = ["MGMT"] if nsip["ipaddress"] == adc["mgmt_ip_address"] else []
                    _tags = ["MIP"] if nsip["type"] == "MIP" else _tags
                    record = {
                        "vlan": port["vlan"],
                        "ipaddress": nsip["ipaddress"],
                        "netmask": netmask_to_cidr(nsip["netmask"]),
                        "port": port["port"],
                        "version": 4,
                        "tags": _tags,
                    }
                    ports.append(record)
    return ports


def parse_nsip6s(nsip6s: List[dict], ports: List[dict]) -> List[dict]:
    """Parse Netscaler IPv6 Addresses."""
    for nsip6 in nsip6s:
        if nsip6["scope"] == "link-local":
            vlan = nsip6["vlan"]
            ipaddress, netmask = nsip6["ipv6address"].split("/")
            port = "L0/1"
            record = {"vlan": vlan, "ipaddress": ipaddress, "netmask": netmask, "port": port}
            ports.append(record)

    return ports
