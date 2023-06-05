"""All interactions with infoblox."""  # pylint: disable=too-many-lines

import copy
import json
import ipaddress
import logging
import re
import urllib.parse
import requests
from requests.exceptions import HTTPError
from requests.compat import urljoin
from dns import reversename
from nautobot.core.settings_funcs import is_truthy
from nautobot_ssot_infoblox.constant import PLUGIN_CFG
from nautobot_ssot_infoblox.utils.diffsync import get_ext_attr_dict

logger = logging.getLogger(__name__)


def parse_url(address):
    """Handle outside case where protocol isn't included in URL address.

    Args:
        address (str): URL set by end user for Infoblox instance.

    Returns:
        ParseResult: The parsed results from urllib.
    """
    if not re.search(r"^[A-Za-z0-9+.\-]+://", address):
        address = f"https://{address}"
    return urllib.parse.urlparse(address)


def get_default_ext_attrs(review_list: list) -> dict:
    """Determine the default Extensibility Attributes for an object being processed.

    Args:
        review_list (list): The list of objects that need to be reviewed to gather default Extensibility Attributes.

    Returns:
        dict: Dictionary of default Extensibility Attributes for a VLAN View, VLANs, Prefixes, or IP Addresses.
    """
    default_ext_attrs = {}
    for item in review_list:
        pf_ext_attrs = get_ext_attr_dict(extattrs=item.get("extattrs", {}))
        for attr in pf_ext_attrs:
            if attr not in default_ext_attrs:
                default_ext_attrs[attr] = None
    return default_ext_attrs


def get_dns_name(possible_fqdn: str) -> str:
    """Validate passed FQDN and returns if found.

    Args:
        possible_fqdn (str): Potential string to be used for IP Address dns_name.

    Returns:
        str: Validated FQDN or blank string if not valid.
    """
    dns_name = ""
    # validate that the FQDN attempting to be imported is valid
    if re.match(
        pattern=r"(?=^.{1,253}$)(^(((?!-)[a-zA-Z0-9-]{1,63}(?<!-))|((?!-)[a-zA-Z0-9-]{1,63}(?<!-)\.)+[a-zA-Z]{2,63})$)",
        string=possible_fqdn,
    ):
        return possible_fqdn
    # if dns_name is just some text with spaces, replace spaces with underscore
    if " " in possible_fqdn and "." not in possible_fqdn:
        dns_name = possible_fqdn.replace("(", "").replace(")", "").replace(" ", "_")
    else:
        # if FQDN isn't valid than we need to strip the invalid part
        match = re.match(pattern="^(?P<fqdn>[0-9A-Za-z._-]+)", string=possible_fqdn)
        if match:
            dns_name = match.group("fqdn")
    return dns_name


class InvalidUrlScheme(Exception):
    """Exception raised for wrong scheme being passed for URL.

    Attributes:
        message (str): Returned explanation of Error.
    """

    def __init__(self, scheme):
        """Initialize Exception with wrong scheme in message."""
        self.message = f"Invalid URL scheme '{scheme}' found for Infoblox URL. Please correct to use HTTPS."
        super().__init__(self.message)


class InfobloxApi:  # pylint: disable=too-many-public-methods,  too-many-instance-attributes
    """Representation and methods for interacting with Infoblox."""

    def __init__(
        self,
        url=PLUGIN_CFG.get("NAUTOBOT_INFOBLOX_URL"),
        username=PLUGIN_CFG.get("NAUTOBOT_INFOBLOX_USERNAME"),
        password=PLUGIN_CFG.get("NAUTOBOT_INFOBLOX_PASSWORD"),
        verify_ssl=is_truthy(PLUGIN_CFG.get("NAUTOBOT_INFOBLOX_VERIFY_SSL")),
        wapi_version=PLUGIN_CFG.get("NAUTOBOT_INFOBLOX_WAPI_VERSION"),
        cookie=None,
    ):  # pylint: disable=too-many-arguments
        """Initialize Infoblox class."""
        parsed_url = parse_url(url.strip())
        if parsed_url.scheme != "https":
            if parsed_url.scheme == "http":
                self.url = parsed_url._replace(scheme="https").geturl()
            else:
                raise InvalidUrlScheme(scheme=parsed_url.scheme)
        else:
            self.url = parsed_url.geturl()
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.wapi_version = wapi_version
        self.cookie = cookie
        if self.verify_ssl is False:
            requests.packages.urllib3.disable_warnings(  # pylint: disable=no-member
                requests.packages.urllib3.exceptions.InsecureRequestWarning  # pylint: disable=no-member
            )  # pylint: disable=no-member
        self.headers = {"Content-Type": "application/json"}
        self.extra_vars = {}

    def _request(self, method, path, **kwargs):
        """Return a response object after making a request to by other methods.

        Args:
            method (str): Request HTTP method to call with requests.
            path (str): URL path to call.

        Returns:
            :class:`~requests.Response`: Response from the API.
        """
        kwargs["verify"] = self.verify_ssl
        kwargs["headers"] = self.headers
        api_path = f"/wapi/{self.wapi_version}/{path}"
        url = urljoin(self.url, api_path)

        if self.cookie:
            resp = requests.request(method, url, cookies=self.cookie, **kwargs)
        else:
            kwargs["auth"] = requests.auth.HTTPBasicAuth(self.username, self.password)
            resp = requests.request(method, url, **kwargs)
            self.cookie = copy.copy(resp.cookies.get_dict("ibapauth"))
        resp.raise_for_status()
        return resp

    def _delete(self, resource):
        """Delete a resource from Infoblox.

        Args:
            resource (str): Resource to delete

        Returns:
            (dict or str): Resource JSON/String

        Returns Response:
            "network/ZG5zLm5ldHdvcmskMTkyLjAuMi4wLzI0LzA:192.0.2.0/24/default"
        """
        response = self._request("DELETE", resource)
        try:
            logger.info(response.json())
            return response.json()
        except json.decoder.JSONDecodeError:
            logger.info(response.text)
            return response.text

    def _update(self, resource, **params):
        """Delete a resource from Infoblox.

        Args:
            resource (str): Resource to update
            params (dict): Parameters to update within a resource

        Returns:
            (dict or str): Resource JSON / String

        Returns Response:
            "network/ZG5zLm5ldHdvcmskMTkyLjAuMi4wLzI0LzA:192.0.2.0/24/default"
        """
        response = self._request("PUT", path=resource, params=params)
        try:
            logger.info(response.json())
            return response.json()
        except json.decoder.JSONDecodeError:
            logger.info(response.text)
            return response.text

    def _get_network_ref(self, prefix):  # pylint: disable=inconsistent-return-statements
        """Fetch the _ref of a prefix resource.

        Args:
            prefix (str): IPv4 Prefix to fetch the _ref for.

        Returns:
            (str) network _ref or None

        Returns Response:
            "network/ZG5zLm5ldHdvcmskMTkyLjAuMi4wLzI0LzA:192.0.2.0/24/default"
        """
        for item in self.get_all_subnets(prefix):
            if item["network"] == prefix:
                return item["_ref"]

    def _get_network_container_ref(self, prefix):  # pylint: disable=inconsistent-return-statements
        """Fetch the _ref of a networkcontainer resource.

        Args:
            prefix (str): IPv4 Prefix to fetch the _ref for.

        Returns:
            (str) networkcontainer _ref or None

        Returns Response:
            "networkcontainer/ZG5zLm5ldHdvcmtfY29udGFpbmVyJDE5Mi4xNjguMi4wLzI0LzA:192.168.2.0/24/default"
        """
        for item in self.get_network_containers():
            if item["network"] == prefix:
                return item["_ref"]

    def get_all_ipv4address_networks(self, prefixes):
        """Get all used / unused IPv4 addresses within the supplied network.

        Args:
            prefixes (List[tuple]): List of Network prefixes and associated network view - ('10.220.0.0/22', 'default')

        Returns:
            (list): IPv4 dict objects

        Return Response:
        [
            {
                "_ref": "ipv4address/Li5pcHY0X2FkZHJlc3MkMTAuMjIwLjAuMTAwLzA:10.220.0.100",
                "extattrs": {"Usage": {"value": "TACACS"}},
                "ip_address": "10.220.0.100",
                "is_conflict": false,
                "lease_state": "FREE",
                "mac_address": "55:55:55:55:55:55",
                "names": [],
                "network": "10.220.0.0/22",
                "network_view": "default",
                "objects": [
                    "fixedaddress/ZG5zLmZpeGVkX2FkZHJlc3MkMTAuMjIwLjAuMTAwLjAuLg:10.220.0.100/default"
                ],
                "status": "USED",
                "types": [
                    "FA",
                    "RESERVED_RANGE"
                ],
                "usage": [
                    "DHCP"
                ]
            },
            {
                "_ref": "ipv4address/Li5pcHY0X2FkZHJlc3MkMTAuMjIwLjAuMTAxLzA:10.220.0.101",
                "extattrs": {},
                "ip_address": "10.220.0.101",
                "is_conflict": false,
                "lease_state": "FREE",
                "mac_address": "11:11:11:11:11:11",
                "names": [
                    "testdevice1.test"
                ],
                "network": "10.220.0.0/22",
                "network_view": "default",
                "objects": [
                    "record:host/ZG5zLmhvc3QkLl9kZWZhdWx0LnRlc3QudGVzdGRldmljZTE:testdevice1.test/default"
                ],
                "status": "USED",
                "types": [
                    "HOST",
                    "RESERVED_RANGE"
                ],
                "usage": [
                    "DNS",
                    "DHCP"
                ]
            }
        ]
        """

        def get_ipaddrs(url_path: str, data: dict) -> list:
            """Retrieve IP addresses specified in data payload.

            Args:
                url_path (str): The URL path to the API endpoint for requests.
                data (dict): The data payload query of IP Addresses.

            Returns:
                list: List of dicts of IP Addresses for the specified prefixes or an empty list if no response.
            """
            response = None
            try:
                response = self._request(method="POST", path=url_path, data=data)
            except HTTPError as err:
                logger.info(err.response.text)
            if response and len(response.json()) > 0:
                logger.debug(response.json()[0])
                return response.json()[0]
            return []

        def create_payload(prefix: str, view: str) -> dict:
            """Create the payload structure for querying IP Addresses from subnets.

            Args:
                prefix (str): The prefix to get IP addresses for.
                view (str): The Network View of the prefix being queried.

            Returns:
                dict: Dictionary containing query parameters for IP addresses from a prefix intended to be part of a list sent to request endpoint.
            """
            query = {
                "method": "GET",
                "object": "ipv4address",
                "data": {"network_view": view, "network": prefix, "status": "USED"},
                "args": {
                    "_return_fields": "ip_address,mac_address,names,network,objects,status,types,usage,comment,extattrs"
                },
            }
            return query

        url_path = "request"
        payload, ipaddrs = [], []
        num_hosts = 0
        for prefix in prefixes:
            view = prefix[1]
            network = ipaddress.ip_network(prefix[0])
            # Due to default of 1000 max_results from Infoblox we must specify a max result limit or limit response to 1000.
            # Make individual request if it's larger than 1000 hosts and specify max result limit to be number of hosts in prefix.
            if network.num_addresses > 1000:
                pf_payload = create_payload(prefix=prefix[0], view=view)
                pf_payload["args"]["_max_results"] = network.num_addresses
                addrs = get_ipaddrs(url_path=url_path, data=json.dumps([pf_payload]))
                if addrs:
                    ipaddrs = ipaddrs + addrs
                continue

            # append payloads to list until number of hosts is 1000
            if network.num_addresses + num_hosts <= 1000:
                num_hosts += network.num_addresses
                payload.append(create_payload(prefix=prefix[0], view=view))
            else:
                # if we can't add more hosts, make call to get IP addresses with existing payload
                addrs = get_ipaddrs(url_path=url_path, data=json.dumps(payload))
                if addrs:
                    ipaddrs = ipaddrs + addrs
                # reset payload as all addresses are processed
                payload = []
                payload.append(create_payload(prefix=prefix[0], view=view))
                num_hosts = network.num_addresses
            # check if last prefix in list, if it is, send payload otherwise keep processing
            if prefixes[-1] == prefix:
                addrs = get_ipaddrs(url_path=url_path, data=json.dumps(payload))
                if addrs:
                    ipaddrs = ipaddrs + addrs
                payload = []
                num_hosts = 0
        return ipaddrs

    def create_network(self, prefix, comment=None):
        """Create a network.

        Args:
            prefix (str): IP network to create.

        Returns:
            (str) of reference network

        Return Response:
            "network/ZG5zLm5ldHdvcmskMTkyLjE2OC4wLjAvMjMvMA:192.168.0.0/23/default"
        """
        params = {"network": prefix, "comment": comment}
        api_path = "network"
        response = self._request("POST", api_path, params=params)
        logger.info(response.text)
        return response.text

    def delete_network(self, prefix):
        """Delete a network.

        Args:
            prefix (str): IPv4 prefix to delete.

        Returns:
            (dict) deleted prefix.

        Returns Response:
            {"deleted": "network/ZG5zLm5ldHdvcmskMTkyLjAuMi4wLzI0LzA:192.0.2.0/24/default"}
        """
        resource = self._get_network_ref(prefix)

        if resource:
            self._delete(resource)
            response = {"deleted": resource}
        else:
            response = {"error": f"{prefix} not found."}

        logger.info(response)
        return response

    def update_network(self, prefix, comment=None):
        """Update a network.

        Args:
            (str): IPv4 prefix to update.
            comment (str): IPv4 prefix update comment.

        Returns:
            (dict) updated prefix.

        Return Response:
            {"updated": "network/ZG5zLm5ldHdvcmskMTkyLjE2OC4wLjAvMjMvMA:192.168.0.0/23/default"}
        """
        resource = self._get_network_ref(prefix)

        if resource:
            params = {"network": prefix, "comment": comment}
            self._update(resource, **params)
            response = {"updated": resource}
        else:
            response = {"error": f"error updating {prefix}"}
        logger.info(response)
        return response

    def create_network_container(self, prefix, comment=None):
        """Create a network container.

        Args:
            prefix (str): IP network to create.

        Returns:
            (str) of reference network

        Return Response:
            "networkcontainer/ZG5zLm5ldHdvcmskMTkyLjE2OC4wLjAvMjMvMA:192.168.0.0/23/default"
        """
        params = {"network": prefix, "comment": comment}
        api_path = "networkcontainer"
        response = self._request("POST", api_path, params=params)
        logger.info(response.text)
        return response.text

    def delete_network_container(self, prefix):
        """Delete a network container.

        Args:
            prefix (str): IPv4 prefix to delete.

        Returns:
            (dict) deleted prefix.

        Returns Response:
            {"deleted": "networkcontainer/ZG5zLm5ldHdvcmskMTkyLjAuMi4wLzI0LzA:192.0.2.0/24/default"}
        """
        resource = self._get_network_container_ref(prefix)

        if resource:
            self._delete(resource)
            response = {"deleted": resource}
        else:
            response = {"error": f"{prefix} not found."}

        logger.info(response)
        return response

    def update_network_container(self, prefix, comment=None):
        """Update a network container.

        Args:
            (str): IPv4 prefix to update.
            comment (str): IPv4 prefix update comment.

        Returns:
            (dict) updated prefix.

        Return Response:
            {"updated": "networkcontainer/ZG5zLm5ldHdvcmskMTkyLjE2OC4wLjAvMjMvMA:192.168.0.0/23/default"}
        """
        resource = self._get_network_container_ref(prefix)

        if resource:
            params = {"network": prefix, "comment": comment}
            self._update(resource, **params)
            response = {"updated": resource}
        else:
            response = {"error": f"error updating {prefix}"}
        logger.info(response)
        return response

    def get_host_record_by_name(self, fqdn):
        """Get the host record by using FQDN.

        Args:
            fqdn (str): IPv4 Address to look up

        Returns:
            (list) of record dicts

        Return Response:
        [
            {
                "_ref": "record:host/ZG5zLmhvc3QkLl9kZWZhdWx0LnRlc3QudGVzdGRldmljZTE:testdevice1.test/default",
                "ipv4addrs": [
                    {
                        "_ref": "record:host_ipv4addr/ZG5zLmhvc3RfYWRkcmVzcyQuX2RlZmF1bHQudGVzdC50ZXN0ZGV2aWNlMS4xMC4yMjAuMC4xMDEu:10.220.0.101/testdevice1.test/default",
                        "configure_for_dhcp": true,
                        "host": "testdevice1.test",
                        "ipv4addr": "10.220.0.101",
                        "mac": "11:11:11:11:11:11"
                    }
                ],
                "name": "testdevice1.test",
                "view": "default"
            }
        ]
        """
        url_path = "record:host"
        params = {"name": fqdn, "_return_as_object": 1}
        response = self._request("GET", url_path, params=params)
        logger.info(response.json)
        return response.json().get("result")

    def get_host_record_by_ip(self, ip_address):
        """Get the host record by using IP Address.

        Args:
            ip_address (str): IPv4 Address to look up

        Returns:
            (list) of record dicts

        Return Response:
        [
            {
                "_ref": "record:host/ZG5zLmhvc3QkLl9kZWZhdWx0LnRlc3QudGVzdGRldmljZTE:testdevice1.test/default",
                "ipv4addrs": [
                    {
                        "_ref": "record:host_ipv4addr/ZG5zLmhvc3RfYWRkcmVzcyQuX2RlZmF1bHQudGVzdC50ZXN0ZGV2aWNlMS4xMC4yMjAuMC4xMDEu:10.220.0.101/testdevice1.test/default",
                        "configure_for_dhcp": true,
                        "host": "testdevice1.test",
                        "ipv4addr": "10.220.0.101",
                        "mac": "11:11:11:11:11:11"
                    }
                ],
                "name": "testdevice1.test",
                "view": "default"
            }
        ]
        """
        url_path = "record:host"
        params = {"ipv4addr": ip_address, "_return_as_object": 1}
        response = self._request("GET", url_path, params=params)
        logger.info(response.json)
        return response.json().get("result")

    def get_a_record_by_name(self, fqdn):
        """Get the A record for a FQDN.

        Args:
            fqdn (str): "testdevice1.test"

        Returns:
            (list) of record dicts

        Return Response:
        [
            {
                "_ref": "record:a/ZG5zLmJpbmRfYSQuX2RlZmF1bHQudGVzdCx0ZXN0ZGV2aWNlMSwxMC4yMjAuMC4xMDE:testdevice1.test/default",
                "ipv4addr": "10.220.0.101",
                "name": "testdevice1.test",
                "view": "default"
            }
        ]
        """
        url_path = "record:a"
        params = {"name": fqdn, "_return_as_object": 1}
        response = self._request("GET", url_path, params=params)
        logger.info(response.json)
        return response.json().get("result")

    def get_a_record_by_ip(self, ip_address):
        """Get the A record for a IP Address.

        Args:
            ip_address (str): "10.220.0.101"

        Returns:
            (list) of record dicts

        Return Response:
        [
            {
                "_ref": "record:a/ZG5zLmJpbmRfYSQuX2RlZmF1bHQudGVzdCx0ZXN0ZGV2aWNlMSwxMC4yMjAuMC4xMDE:testdevice1.test/default",
                "ipv4addr": "10.220.0.101",
                "name": "testdevice1.test",
                "view": "default"
            }
        ]
        """
        url_path = "record:a"
        params = {"ipv4addr": ip_address, "_return_as_object": 1}
        response = self._request("GET", url_path, params=params)
        logger.info(response.json)
        return response.json().get("result")

    def get_ptr_record_by_name(self, fqdn):
        """Get the PTR record by FQDN.

        Args:
            fqdn (str): "testdevice1.test"

        Returns:
            (list) of record dicts

        Return Response:
        [
            {
                "_ref": "record:ptr/ZG5zLmJpbmRfcHRyJC5fZGVmYXVsdC50ZXN0LjEwMS4wLjIyMC4xMC50ZXN0ZGV2aWNlMS50ZXN0:10.220.0.101.test/default",
                "ptrdname": "testdevice1.test",
                "view": "default"
            }
        ]
        """
        url_path = "record:ptr"
        params = {"ptrdname": fqdn, "_return_as_object": 1}
        response = self._request("GET", url_path, params=params)
        logger.info(response.json)
        return response.json().get("result")

    def get_all_dns_views(self):
        """Get all dns views.

        Returns:
            (list) of record dicts

        Return Response:
        [
            {
                "_ref": "view/ZG5zLnZpZXckLl9kZWZhdWx0:default/true",
                "is_default": true,
                "name": "default"
            },
            {
                "_ref": "view/ZG5zLnZpZXckLjE:default.operations/false",
                "is_default": false,
                "name": "default.operations"
            }
        ]
        """
        url_path = "view"
        params = {"_return_as_object": 1}
        response = self._request("GET", url_path, params=params)
        logger.info(response.json)
        return response.json().get("result")

    def create_a_record(self, fqdn, ip_address):
        """Create an A record for a given FQDN.

        Please note:  This API call with work only for host records that do not have an associated a record.
        If an a record already exists, this will return a 400 error.

        Returns:
            Dict: Dictionary of _ref and name

        Return Response:
        {
            "_ref": "record:a/ZG5zLmJpbmRfYSQuX2RlZmF1bHQudGVzdCx0ZXN0ZGV2aWNlMiwxMC4yMjAuMC4xMDI:testdevice2.test/default",
            "name": "testdevice2.test"
        }
        """
        url_path = "record:a"
        params = {"_return_fields": "name", "_return_as_object": 1}
        payload = {"name": fqdn, "ipv4addr": ip_address}
        response = self._request("POST", url_path, params=params, json=payload)
        logger.info(response.json)
        return response.json().get("result")

    def get_dhcp_lease(self, lease_to_check):
        """Get a DHCP lease for the IP/hostname passed in.

        Args:
            lease_to_check (str): "192.168.0.1" or "testdevice1.test"

        Returns:
            Output of
                get_dhcp_lease_from_ipv4
                    or
                get_dhcp_lease_from_hostname
        """
        ips = len(
            re.findall(
                r"(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)",
                lease_to_check,
            )
        )
        if ips > 0:
            return self.get_dhcp_lease_from_ipv4(lease_to_check)
        return self.get_dhcp_lease_from_hostname(lease_to_check)

    def get_dhcp_lease_from_ipv4(self, ip_address):
        """Get a DHCP lease for the IP address passed in.

        Args:
            ip_address (str): "192.168.0.1"

        Returns:
            (list) of record dicts

        Return Response:
        [
            {
                '_ref': 'lease/ZG5zLmxlYXNlJDQvMTcyLjE2LjIwMC4xMDEvMC8:172.26.1.250/default1',
                'binding_state': 'ACTIVE',
                'fingerprint': 'Cisco/Linksys SPA series IP Phone',
                'hardware': '16:55:a4:1b:98:c9'
            }
        ]
        """
        url_path = "lease"
        params = {
            "address": ip_address,
            "_return_fields": "binding_state,hardware,client_hostname,fingerprint",
            "_return_as_object": 1,
        }
        response = self._request("GET", url_path, params=params)
        logger.info(response.json)
        return response.json()

    def get_dhcp_lease_from_hostname(self, hostname):
        """Get a DHCP lease for the hostname passed in.

        Args:
            hostnames (str): "testdevice1.test"

        Returns:
            (list) of record dicts

        Return Response:
        [
            {
                "_ref": "lease/ZG5zLmxlYXNlJC8xOTIuMTY4LjQuMy8wLzE3:192.168.4.3/Company%201",
                "binding_state": "STATIC",
                "client_hostname": "test",
                "hardware": "12:34:56:78:91:23"
            }
        ]
        """
        url_path = "lease"
        params = {
            "client_hostname": hostname,
            "_return_fields": "binding_state,hardware,client_hostname,fingerprint",
            "_return_as_object": 1,
        }
        response = self._request("GET", url_path, params=params)
        logger.info(response.json)
        return response.json()

    def get_all_subnets(self, prefix: str = None):
        """Get all Subnets.

        Args:
            prefix (str): Network prefix - '10.220.0.0/22'

        Returns:
            (list) of record dicts

        Return Response:
        [
            {
                "_ref": "network/ZG5zLm5ldHdvcmskMTAuMjIzLjAuMC8yMS8w:10.223.0.0/21/default",
                "extattrs": {},
                "network": "10.223.0.0/21",
                "network_view": "default",
                "rir": "NONE",
                "vlans": [],
            },
            {
                "_ref": "network/ZG5zLm5ldHdvcmskMTAuMjIwLjY0LjAvMjEvMA:10.220.64.0/21/default",
                "extattrs": {},
                "network": "10.220.64.0/21",
                "network_view": "default",
                "rir": "NONE",
                "vlans": [],
            },
        ]
        """
        url_path = "network"
        params = {
            "_return_as_object": 1,
            "_return_fields": "network,network_view,comment,extattrs,rir_organization,rir,vlans",
            "_max_results": 10000,
        }

        if prefix:
            params.update({"network": prefix})
        try:
            response = self._request("GET", url_path, params=params)
        except HTTPError as err:
            logger.info(err.response.text)
            return []
        logger.info(response.json())
        return response.json().get("result")

    def get_authoritative_zone(self):
        """Get authoritative zone to check if fqdn exists.

        Returns:
            (list) of zone dicts

        Return Response:
        [
            {
                "_ref": "zone_auth/ZG5zLnpvbmUkLl9kZWZhdWx0LnRlc3Qtc2l0ZS1pbm5hdXRvYm90:test-site-innautobot/default",
                "fqdn": "test-site-innautobot",
                "view": "default"
            },
            {
                "_ref": "zone_auth/ZG5zLnpvbmUkLl9kZWZhdWx0LnRlc3Qtc2l0ZQ:test-site/default",
                "fqdn": "test-site",
                "view": "default"
            },
        ]
        """
        url_path = "zone_auth"
        params = {"_return_as_object": 1}
        response = self._request("GET", url_path, params=params)
        logger.info(response.json())
        return response.json().get("result")

    def _find_network_reference(self, network):
        """Find the reference for the given network.

        Returns:
            Dict: Dictionary of _ref and name

        Return Response:
        [
            {
                "_ref": "network/ZG5zLm5ldHdvcmskMTAuMjIwLjAuMC8yMi8w:10.220.0.0/22/default",
                "network": "10.220.0.0/22",
                "network_view": "default"
            }
        ]
        """
        url_path = "network"
        params = {"network": network}
        response = self._request("GET", url_path, params=params)
        logger.info(response.json())
        return response.json()

    def find_next_available_ip(self, network):
        """Find the next available ip address for a given network.

        Returns:
            Dict:

        Return Response:
        {
            "ips": [
                "10.220.0.1"
            ]
        }
        """
        next_ip_avail = ""
        # Find the Network reference id
        try:
            network_ref_id = self._find_network_reference(network)
        except Exception as err:  # pylint: disable=broad-except
            logger.warning("Network reference not found for %s: %s", network, err)
            return next_ip_avail

        if network_ref_id and isinstance(network_ref_id, list):
            network_ref_id = network_ref_id[0].get("_ref")
            url_path = network_ref_id
            params = {"_function": "next_available_ip"}
            payload = {"num": 1}
            response = self._request("POST", url_path, params=params, json=payload)
            logger.info(response.json())
            next_ip_avail = response.json().get("ips")[0]

        return next_ip_avail

    def reserve_fixed_address(self, network, mac_address):
        """Reserve the next available ip address for a given network range.

        Returns:
            Str: The IP Address that was reserved

        Return Response:
            "10.220.0.1"
        """
        # Get the next available IP Address for this network
        ip_address = self.find_next_available_ip(network)
        if ip_address:
            url_path = "fixedaddress"
            params = {"_return_fields": "ipv4addr", "_return_as_object": 1}
            payload = {"ipv4addr": ip_address, "mac": mac_address}
            response = self._request("POST", url_path, params=params, json=payload)
            logger.info(response.json())
            return response.json().get("result").get("ipv4addr")
        return False

    def create_fixed_address(self, ip_address, mac_address):
        """Create a fixed ip address within Infoblox.

        Returns:
            Str: The IP Address that was reserved

        Return Response:
            "10.220.0.1"
        """
        url_path = "fixedaddress"
        params = {"_return_fields": "ipv4addr", "_return_as_object": 1}
        payload = {"ipv4addr": ip_address, "mac": mac_address}
        response = self._request("POST", url_path, params=params, json=payload)
        logger.info(response.json())
        return response.json().get("result").get("ipv4addr")

    def create_host_record(self, fqdn, ip_address):
        """Create a host record for a given FQDN.

        Please note:  This API call with work only for host records that do not have an associated a record.
        If an a record already exists, this will return a 400 error.

        Returns:
            Dict: Dictionary of _ref and name

        Return Response:
        {

            "_ref": "record:host/ZG5zLmhvc3QkLjEuY29tLmluZm9ibG94Lmhvc3Q:host.infoblox.com/default.test",
            "name": "host.infoblox.com",
        }
        """
        url_path = "record:host"
        params = {"_return_fields": "name", "_return_as_object": 1}
        payload = {"name": fqdn, "configure_for_dns": False, "ipv4addrs": [{"ipv4addr": ip_address}]}
        try:
            response = self._request("POST", url_path, params=params, json=payload)
        except HTTPError as err:
            logger.info("Host record error: %s", err.response.text)
            return []
        logger.info("Infoblox host record created: %s", response.json())
        return response.json().get("result")

    def delete_host_record(self, ip_address):
        """Delete provided IP Address from Infoblox."""
        resource = self.get_host_record_by_ip(ip_address)
        if resource:
            ref = resource[0]["_ref"]
            self._delete(ref)
            response = {"deleted": ip_address}
        else:
            response = {"error": f"Did not find {ip_address}"}
        logger.info(response)
        return response

    def create_ptr_record(self, fqdn, ip_address):
        """Create an PTR record for a given FQDN.

        Args:
            fqdn (str): Fully Qualified Domain Name
            ip_address (str): Host IP address

        Returns:
            Dict: Dictionary of _ref and name

        Return Response:
        {
            "_ref": "record:ptr/ZG5zLmJpbmRfcHRyJC5fZGVmYXVsdC5hcnBhLmluLWFkZHIuMTAuMjIzLjkuOTYucjQudGVzdA:96.9.223.10.in-addr.arpa/default",
            "ipv4addr": "10.223.9.96",
            "name": "96.9.223.10.in-addr.arpa",
            "ptrdname": "r4.test"
        }
        """
        url_path = "record:ptr"
        params = {"_return_fields": "name,ptrdname,ipv4addr", "_return_as_object": 1}
        reverse_host = str(reversename.from_address(ip_address))[
            0:-1
        ]  # infoblox does not accept the top most domain '.', so we strip it
        payload = {"name": reverse_host, "ptrdname": fqdn, "ipv4addr": ip_address}
        response = self._request("POST", url_path, params=params, json=payload)
        logger.info("Infoblox PTR record created: %s", response.json())
        return response.json().get("result")

    def search_ipv4_address(self, ip_address):
        """Find if IP address is in IPAM. Returns empty list if address does not exist.

        Returns:
            (list) of record dicts

        Return Response:
        [
            {
                "_ref": "record:host/ZG5zLmhvc3QkLl9kZWZhdWx0LnRlc3Qtc2l0ZS1pbm5hdXRvYm90LnRlc3QtZGV2aWNl:test-device.test-site-innautobot/default",
                "ipv4addrs": [
                    {
                        "_ref": "record:host_ipv4addr/ZG5zLmhvc3RfYWRkcmVzcyQuX2RlZmF1bHQudGVzdC1zaXRlLWlubmF1dG9ib3QudGVzdC1kZXZpY2UuMTAuMjIzLjAuNDIu:10.223.0.42/test-device.test-site-innautobot/default",
                        "configure_for_dhcp": false,
                        "host": "test-device.test-site-innautobot",
                        "ipv4addr": "10.223.0.42"
                    }
                ],
                "name": "test-device.test-site-innautobot",
                "view": "default"
            },
            {
                "_ref": "networkcontainer/ZG5zLm5ldHdvcmtfY29udGFpbmVyJDEwLjIyMy4wLjAvMTYvMA:10.223.0.0/16/default",
                "network": "10.223.0.0/16",
                "network_view": "default"
            }
        ]
        """
        url_path = "search"
        params = {"address": ip_address, "_return_as_object": 1}
        response = self._request("GET", url_path, params=params)
        logger.info(response.json())
        return response.json().get("result")

    def get_vlan_view(self, name="Nautobot"):
        """Retrieve a specific vlanview.

        Args:
            name (str): Name of the vlan view

        Returns:
            (dict): Vlan view resource.

        Returns Response:
            [
                {
                    "_ref": "vlanview/ZG5zLnZsYW5fdmlldyROYXV0b2JvdC4xLjQwOTQ:Nautobot/1/4094",
                    "end_vlan_id": 4094,
                    "name": "Nautobot",
                    "start_vlan_id": 1
                }
            ]
        """
        url_path = "vlanview"
        params = {"name": name}
        response = self._request("GET", path=url_path, params=params)
        logger.info(response.json())
        return response.json()

    def create_vlan_view(self, name, start_vid=1, end_vid=4094):
        """Create a vlan view.

        Args:
            name (str): Name of the vlan view.
            start_vid (int): Start vlan id
            end_vid (int): End vlan id

        Returns:
            (dict): reference vlan view resource

        Returns Response:
            {"result": "vlanview/ZG5zLnZsYW5fdmlldyR0ZXN0LjEuNDA5NA:test/1/4094"}
        """
        url_path = "vlanview"
        params = {"name": name, "start_vlan_id": start_vid, "end_vlan_id": end_vid}
        response = self._request("POST", path=url_path, params=params)
        logger.info(response.json())
        return response.json()

    def get_vlanviews(self):
        """Retrieve all VLANViews from Infoblox.

        Returns:
            List: list of dictionaries

        Return Response:
        [
            {
                "_ref": "vlanview/ZG5zLnZsYW5fdmlldyRWTFZpZXcxLjEwLjIw:VLView1/10/20",
                "extattrs": {},
                "end_vlan_id": 20,
                "name": "VLView1",
                "start_vlan_id": 10
            },
            {
                "_ref": "vlanview/ZG5zLnZsYW5fdmlldyROYXV0b2JvdC4xLjQwOTQ:Nautobot/1/4094",
                "extattrs": {},
                "end_vlan_id": 4094,
                "name": "Nautobot",
                "start_vlan_id": 1
            }
        ]
        """
        url_path = "vlanview"
        params = {"_return_fields": "name,comment,start_vlan_id,end_vlan_id,extattrs"}
        response = self._request("GET", url_path, params=params)
        logger.info(response.json())
        return response.json()

    def get_vlans(self):
        """Retrieve all VLANs from Infoblox.

        Returns:
            List: list of dictionaries

        Return Response:
        [
            {
                "_ref": "vlan/ZG5zLnZsYW4kLmNvbS5pbmZvYmxveC5kbnMudmxhbl92aWV3JGRlZmF1bHQuMS40MDk0LjIw:default/DATA_VLAN/20",
                "extattrs": {},
                "assigned_to": [
                    "network/ZG5zLm5ldHdvcmskMTkyLjE2OC4xLjAvMjQvMA:192.168.1.0/24/default"
                ],
                "description": "PC Users",
                "id": 20,
                "name": "DATA_VLAN",
                "reserved": false,
                "status": "ASSIGNED"
            },
            {
                "_ref": "vlan/ZG5zLnZsYW4kLmNvbS5pbmZvYmxveC5kbnMudmxhbl92aWV3JGRlZmF1bHQuMS40MDk0Ljk5:default/VOICE_VLAN/99",
                "extattrs": {},
                "comment": "Only Cisco IP Phones",
                "id": 99,
                "name": "VOICE_VLAN",
                "reserved": false,
                "status": "UNASSIGNED"
            }
        ]
        """
        url_path = "request"
        payload = json.dumps(
            [
                {
                    "method": "GET",
                    "object": "vlan",
                    "data": {},
                    "args": {
                        "_max_results": 100000000,
                        "_return_fields": "assigned_to,id,name,comment,contact,department,description,reserved,status,extattrs",
                    },
                }
            ]
        )
        response = self._request("POST", url_path, data=payload)
        logger.info(response.json()[0])
        return response.json()[0]

    def create_vlan(self, vlan_id, vlan_name, vlan_view):
        """Create a VLAN in Infoblox.

        Args:
            vlan_id (Int): VLAN ID (1-4094)
            vlan_name (Str): VLAN name
            vlan_view (Str): The vlan view name

        Returns:
            Str: _ref to created vlan

        Return Response:
        "vlan/ZG5zLnZsYW4kLmNvbS5pbmZvYmxveC5kbnMudmxhbl92aWV3JFZMVmlldzEuMTAuMjAuMTE:VLView1/test11/11"
        """
        parent = self.get_vlan_view(name=vlan_view)

        if len(parent) == 0:
            parent = self.create_vlan_view(name=vlan_view).get("result")
        else:
            parent = parent[0].get("_ref")

        url_path = "vlan"
        params = {}
        payload = {"parent": parent, "id": vlan_id, "name": vlan_name}
        response = self._request("POST", url_path, params=params, json=payload)
        logger.info(response.json())
        return response.json()

    @staticmethod
    def get_ipaddr_status(ip_record: dict) -> str:
        """Determine the IPAddress status based upon types and usage keys."""
        if "DHCP" in ip_record["usage"]:
            return "DHCP"
        return "Active"

    def _find_resource(self, resource, **params):
        """Find the resource for given parameters.

        Returns:
            str: _ref of an object

        Return Response:
            _ref: fixedaddress/ZG5zLmZpeGVkX2FkZHJlc3MkMTAuMjIwLjAuMy4wLi4:10.220.0.3/default
        """
        response = self._request("GET", resource, params=params)
        logger.info(response.json())
        for _resource in response.json():
            return _resource.get("_ref")
        return response.json()

    # TODO: See if we should accept params dictionary and extended to both host record and fixed address
    def update_ipaddress(self, ip_address, **data):  # pylint: disable=inconsistent-return-statements
        """Update a Network object with a given prefix.

        Args:
            prefix (str): Valid IP prefix
            data (dict): keyword args used to update the object e.g. comment="updateme"

        Returns:
            Dict: Dictionary of _ref and name

        Return Response:
        {
            "_ref": "fixedaddress/ZG5zLmZpeGVkX2FkZHJlc3MkMTAuMjIwLjAuMy4wLi4:10.220.0.3/default",
            "ipv4addr": "10.220.0.3"
        }
        """
        resource = self._find_resource("search", address=ip_address)
        if not resource:
            return
        # params = {"_return_fields": "ipv4addr", "_return_as_object": 1}
        params = {}
        try:
            logger.info(data)
            response = self._request("PUT", path=resource, params=params, json=data["data"])
        except HTTPError as err:
            logger.info("Resource: %s", resource)
            logger.info("Could not update IP address: %s", err.response.text)
            return
        logger.info("Infoblox IP Address updated: %s", response.json())
        return response.json()

    def get_network_containers(self):
        """Get all Network Containers.

        Returns:
            (list) of record dicts

        Return Response:
        [
            {
                "_ref": "networkcontainer/ZG5zLm5ldHdvcmtfY29udGFpbmVyJDE5Mi4xNjguMi4wLzI0LzA:192.168.2.0/24/default",
                "comment": "Campus LAN",
                "extattrs": {},
                "network": "192.168.2.0/24",
                "network_view": "default",
                "rir": "NONE",
            }
        ]
        """
        url_path = "networkcontainer"
        params = {
            "_return_as_object": 1,
            "_return_fields": "network,comment,network_view,extattrs,rir_organization,rir",
            "_max_results": 100000,
        }
        response = self._request("GET", url_path, params=params)
        response = response.json()
        logger.info(response)
        results = response.get("result", [])
        for res in results:
            res.update({"status": "container"})
        return results
