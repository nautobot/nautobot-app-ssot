"""All interactions with infoblox."""  # pylint: disable=too-many-lines

from __future__ import annotations

import json
import ipaddress
import logging
import re
from typing import Optional
import urllib.parse
from collections import defaultdict
from typing import Optional
import requests
from requests.auth import HTTPBasicAuth
from requests.exceptions import HTTPError
from requests.compat import urljoin
from dns import reversename
from nautobot.core.settings_funcs import is_truthy
from nautobot_ssot.integrations.infoblox.constant import PLUGIN_CFG
from nautobot_ssot.integrations.infoblox.utils.diffsync import get_ext_attr_dict

logger = logging.getLogger("nautobot.ssot.infoblox")


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
    """Validates passed FQDN and returns if found.

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
        self.auth = HTTPBasicAuth(username, password)
        self.wapi_version = wapi_version
        self.session = self._init_session(verify_ssl=verify_ssl, cookie=cookie)

    def _init_session(self, verify_ssl: bool, cookie: Optional[dict]) -> requests.Session:
        """Initialize requests Session object that is used across all the API calls.

        Args:
            verify_ssl (bool): whether to verify SSL cert for https calls
            cookie (dict): optional dict with cookies to set on the Session object

        Returns:
            initialized session object
        """
        if verify_ssl is False:
            requests.packages.urllib3.disable_warnings(  # pylint: disable=no-member
                requests.packages.urllib3.exceptions.InsecureRequestWarning  # pylint: disable=no-member
            )  # pylint: disable=no-member
        self.headers = {"Content-Type": "application/json"}
        session = requests.Session()
        if cookie and isinstance(cookie, dict):
            session.cookies.update(cookie)
        session.verify = verify_ssl
        session.headers.update(self.headers)
        session.auth = self.auth

        return session

    def _request(self, method, path, **kwargs):
        """Return a response object after making a request by a specified method.

        Args:
            method (str): Request HTTP method to call with Session.request.
            path (str): URL path to call.

        Returns:
            :class:`~requests.Response`: Response from the API.
        """
        api_path = f"/wapi/{self.wapi_version}/{path}"
        url = urljoin(self.url, api_path)

        if self.session.cookies.get("ibapauth"):
            self.session.auth = None
        else:
            self.session.auth = self.auth

        resp = self.session.request(method, url, timeout=PLUGIN_CFG["infoblox_request_timeout"], **kwargs)
        # Infoblox provides meaningful error messages for error codes >= 400
        if resp.status_code >= 400:
            try:
                err_msg = resp.json()
            except json.decoder.JSONDecodeError:
                err_msg = resp.text
            logger.error(err_msg)
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
            logger.debug(response.json())
            return response.json()
        except json.decoder.JSONDecodeError:
            logger.info(response.text)
            return response.text

    def _update(self, resource, **params):
        """Update a resource in Infoblox.

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
            logger.debug(response.json())
            return response.json()
        except json.decoder.JSONDecodeError:
            logger.info(response.text)
            return response.text

    def _get_network_ref(
        self, prefix, network_view: Optional[str] = None
    ):  # pylint: disable=inconsistent-return-statements
        """Fetch the _ref of a prefix resource.

        Args:
            prefix (str): IPv4 Prefix to fetch the _ref for.
            network_view (str): Network View of the prefix to fetch the _ref for.

        Returns:
            (str) network _ref or None

        Returns Response:
            "network/ZG5zLm5ldHdvcmskMTkyLjAuMi4wLzI0LzA:192.0.2.0/24/default"
        """
        url_path = "network"
        params = {"network": prefix, "_return_as_object": 1}
        if network_view:
            params["network_view"] = network_view
        response = self._request("GET", url_path, params=params)
        try:
            logger.debug(response.json())
            results = response.json().get("result")
        except json.decoder.JSONDecodeError:
            logger.info(response.text)
            return response.text
        if results and len(results):
            return results[0]
        return None

    def _get_network_container_ref(
        self, prefix, network_view: Optional[str] = None
    ):  # pylint: disable=inconsistent-return-statements
        """Fetch the _ref of a networkcontainer resource.

        Args:
            prefix (str): IPv4 Prefix to fetch the _ref for.
            network_view (str): Network View of the prefix to fetch the _ref for.

        Returns:
            (str) networkcontainer _ref or None

        Returns Response:
            "networkcontainer/ZG5zLm5ldHdvcmtfY29udGFpbmVyJDE5Mi4xNjguMi4wLzI0LzA:192.168.2.0/24/default"
        """
        url_path = "networkcontainer"
        params = {"network": prefix, "_return_as_object": 1}
        if network_view:
            params["network_view"] = network_view
        response = self._request("GET", url_path, params=params)
        try:
            logger.debug(response.json())
            results = response.json().get("result")
        except json.decoder.JSONDecodeError:
            logger.info(response.text)
            return response.text
        if results and len(results):
            return results[0]
        return None

    def get_all_ipv4address_networks(self, prefixes):
        """Get all used / unused IPv4 addresses within the supplied networks.

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
                response = self._request(method="POST", path=url_path, json=data)
            except HTTPError as err:
                logger.info(err.response.text)
            if response:
                # This should flatten the results, not return the first entry
                results = []
                for result in response.json():
                    results += result
                logger.debug(results)
                return results
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
                    "_return_fields": "ip_address,mac_address,names,network,network_view,objects,status,types,usage,comment,extattrs"
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
                ipaddrs += get_ipaddrs(url_path=url_path, data=[pf_payload])
            # append payloads to list until number of hosts is 1000
            elif network.num_addresses + num_hosts <= 1000:
                num_hosts += network.num_addresses
                payload.append(create_payload(prefix=prefix[0], view=view))
            else:
                # if we can't add more hosts, make call to get IP addresses with existing payload
                ipaddrs += get_ipaddrs(url_path=url_path, data=payload)
                # reset payload as all addresses are processed
                payload = []
                payload.append(create_payload(prefix=prefix[0], view=view))
                num_hosts = network.num_addresses
            # check if last prefix in list, if it is, send payload otherwise keep processing
            if prefixes[-1] == prefix and payload:
                ipaddrs += get_ipaddrs(url_path=url_path, data=payload)

        return ipaddrs

    def create_network(self, prefix, comment=None, network_view: Optional[str] = None):
        """Create a network.

        Args:
            prefix (str): IP network to create.

        Returns:
            (str) of reference network

        Return Response:
            "network/ZG5zLm5ldHdvcmskMTkyLjE2OC4wLjAvMjMvMA:192.168.0.0/23/default"
        """
        params = {"network": prefix, "comment": comment}
        if network_view:
            params["network_view"] = network_view
        api_path = "network"
        response = self._request("POST", api_path, params=params)
        logger.debug(response.text)
        return response.text

    def delete_network(self, prefix, network_view: Optional[str] = None):
        """Delete a network.

        Args:
            prefix (str): IPv4 prefix to delete.

        Returns:
            (dict) deleted prefix.

        Returns Response:
            {"deleted": "network/ZG5zLm5ldHdvcmskMTkyLjAuMi4wLzI0LzA:192.0.2.0/24/default"}
        """
        resource = self._get_network_ref(prefix=prefix, network_view=network_view)

        if resource:
            self._delete(resource)
            response = {"deleted": resource}
        else:
            response = {"error": f"{prefix} not found."}

        logger.debug(response)
        return response

    def update_network(self, prefix, comment=None, network_view: Optional[str] = None):
        """Update a network.

        Args:
            (str): IPv4 prefix to update.
            comment (str): IPv4 prefix update comment.

        Returns:
            (dict) updated prefix.

        Return Response:
            {"updated": "network/ZG5zLm5ldHdvcmskMTkyLjE2OC4wLjAvMjMvMA:192.168.0.0/23/default"}
        """
        resource = self._get_network_ref(prefix=prefix, network_view=network_view)

        if resource:
            params = {"network": prefix, "comment": comment}
            self._update(resource, **params)
            response = {"updated": resource}
        else:
            response = {"error": f"error updating {prefix}"}
        logger.debug(response)
        return response

    def create_network_container(self, prefix, comment=None, network_view: Optional[str] = None):
        """Create a network container.

        Args:
            prefix (str): IP network to create.

        Returns:
            (str) of reference network

        Return Response:
            "networkcontainer/ZG5zLm5ldHdvcmskMTkyLjE2OC4wLjAvMjMvMA:192.168.0.0/23/default"
        """
        params = {"network": prefix, "comment": comment}
        if network_view:
            params["network_view"] = network_view
        api_path = "networkcontainer"
        response = self._request("POST", api_path, params=params)
        logger.debug(response.text)
        return response.text

    def delete_network_container(self, prefix, network_view: Optional[str] = None):
        """Delete a network container.

        Args:
            prefix (str): IPv4 prefix to delete.

        Returns:
            (dict) deleted prefix.

        Returns Response:
            {"deleted": "networkcontainer/ZG5zLm5ldHdvcmskMTkyLjAuMi4wLzI0LzA:192.0.2.0/24/default"}
        """
        resource = self._get_network_container_ref(prefix=prefix, network_view=network_view)

        if resource:
            self._delete(resource)
            response = {"deleted": resource}
        else:
            nv_msg = f" in network view {network_view}" if network_view else ""
            response = {"error": f"{prefix}{nv_msg} not found."}

        logger.debug(response)
        return response

    def update_network_container(self, prefix, comment=None, network_view: Optional[str] = None):
        """Update a network container.

        Args:
            (str): IPv4 prefix to update.
            comment (str): IPv4 prefix update comment.

        Returns:
            (dict) updated prefix.

        Return Response:
            {"updated": "networkcontainer/ZG5zLm5ldHdvcmskMTkyLjE2OC4wLjAvMjMvMA:192.168.0.0/23/default"}
        """
        resource = self._get_network_container_ref(prefix=prefix, network_view=network_view)

        if resource:
            params = {"comment": comment}
            self._update(resource, **params)
            response = {"updated": resource}
        else:
            nv_msg = f" in network view {network_view}" if network_view else ""
            response = {"error": f"error updating {prefix}{nv_msg}"}
        logger.debug(response)
        return response

    def create_range(self, prefix: str, start: str, end: str, network_view: Optional[str] = None) -> str:
        """Create a range.

        Args:
            prefix: IP network range belongs to.
            start: The starting IP of the range.
            end: The ending IP of the range.

        Returns:
            str: Object reference of range.

        Return Response:
            "range/ZG5zLm5ldHdvcmskMTkyLjE2OC4wLjAvMjMvMA:192.168.0.100/192.168.0.254/default"
        """
        params = {"network": prefix, "start_addr": start, "end_addr": end}
        if network_view:
            params["network_view"] = network_view
        api_path = "range"
        response = self._request("POST", api_path, params=params)
        logger.debug(response.text)
        return response.text

    def get_host_record_by_name(self, fqdn, network_view: Optional[str] = None):
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
        if network_view:
            params["network_view"] = network_view
        response = self._request("GET", url_path, params=params)
        logger.debug(response.json())
        return response.json().get("result")

    def get_host_record_by_ip(self, ip_address, network_view: Optional[str] = None):
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
        if network_view:
            params["network_view"] = network_view
        response = self._request("GET", url_path, params=params)
        logger.debug(response.json())
        return response.json().get("result")

    def get_a_record_by_name(self, fqdn, network_view: Optional[str] = None):
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
        # TODO: This is a bit more complicated. One network view can have multiple DNS views
        # default name for a DNS view for a network view is formed by prepending "default." to the network view name
        if network_view:
            dns_view = self.get_default_dns_view_for_network_view(network_view)
            params["view"] = dns_view
        response = self._request("GET", url_path, params=params)
        logger.debug(response.json())
        return response.json().get("result")

    def get_a_record_by_ip(self, ip_address, network_view: Optional[str] = None):
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
        # TODO: This is a bit more complicated. One network view can have multiple DNS views
        # default name for a DNS view for a network view is formed by prepending "default." to the network view name
        # TODO: Would be interesting to see if we can specify network view in the lookup
        if network_view:
            dns_view = self.get_default_dns_view_for_network_view(network_view)
            params["view"] = dns_view
        response = self._request("GET", url_path, params=params)
        logger.debug(response.json())
        return response.json().get("result")

    def get_ptr_record_by_name(self, fqdn, network_view: Optional[str] = None):
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
        if network_view:
            dns_view = self.get_default_dns_view_for_network_view(network_view)
            params["view"] = dns_view
        response = self._request("GET", url_path, params=params)
        logger.debug(response.json())
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
        params = {"_return_fields": "is_default,name,network_view", "_return_as_object": 1}
        response = self._request("GET", url_path, params=params)
        logger.debug(response.json())
        return response.json().get("result")

    def create_a_record(self, fqdn, ip_address, network_view: Optional[str] = None):
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
        if network_view:
            dns_view = self.get_default_dns_view_for_network_view(network_view)
            payload["view"] = dns_view
        response = self._request("POST", url_path, params=params, json=payload)
        logger.debug(response.json())
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

    def get_dhcp_lease_from_ipv4(self, ip_address, network_view: Optional[str] = None):
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
        if network_view:
            params["network_view"] = network_view
        response = self._request("GET", url_path, params=params)
        logger.debug(response.json())
        return response.json()

    def get_dhcp_lease_from_hostname(self, hostname, network_view: Optional[str] = None):
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
        if network_view:
            params["network_view"] = network_view
        response = self._request("GET", url_path, params=params)
        logger.debug(response.json())
        return response.json()

    def get_all_ranges(
        self, prefix: Optional[str] = None, network_view: Optional[str] = None
    ) -> dict[str, dict[str, list[dict[str, str]]]]:
        """Get all Ranges.

        Args:
            prefix: Network prefix - '10.220.0.0/22'

        Returns:
            dict: The mapping of network_view to prefix to defined ranges.

        Return Response:
        {
            "default": {
                "10.0.0.0/24": ["10.0.0.20-10.0.0.254"],
                "10.10.0.0/23": ["10.10.0.20-10.0.0.255", "10.10.1.20-10.10.1.254"]
            },
            "non-default-view": {
                "192.168.1.0/24": ["192.168.1.50-192.168.1.254"]
            }
        }
        """
        url_path = "range"
        params = {"_return_fields": "network,network_view,start_addr,end_addr", "_max_results": 10000}
        if network_view:
            params["network_view"] = network_view
        if prefix:
            params["network"] = prefix
        try:
            response = self._request("GET", url_path, params=params)
        except HTTPError as err:
            logger.info(err.response.text)
            return {}
        json_response = response.json()
        logger.debug(json_response())
        data = defaultdict(lambda: defaultdict(list))
        for prefix_range in json_response:
            str_range = f"{prefix_range['start_addr']}-{prefix_range['end_addr']}"
            data[prefix_range["network_view"]][prefix_range["network"]].append(str_range)
        return data

    def get_all_subnets(self, prefix: str = None, ipv6: bool = False, network_view: Optional[str] = None):
        """Get all Subnets.

        Args:
            prefix (str): Network prefix - '10.220.0.0/22'
            ipv6 (bool): Whether or not the call should be made for IPv6 subnets.

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
                "ranges": ["10.220.65.0-10.220.66.255"]
            },
        ]
        """
        if ipv6:
            url_path = "ipv6network"
        else:
            url_path = "network"

        params = {
            "_return_fields": "network,network_view,comment,extattrs,rir_organization,rir,vlans",
            "_max_results": 10000,
        }
        if network_view:
            params.update({"network_view": network_view})
        if prefix:
            params.update({"network": prefix})
        try:
            response = self._request("GET", url_path, params=params)
        except HTTPError as err:
            logger.info(err.response.text)
            return []
        json_response = response.json()
        logger.debug(json_response())
        # TODO: What does the below code do? We don't return any of this. @progala
        if not ipv6:
            ranges = self.get_all_ranges(prefix=prefix, network_view=network_view)
            for returned_prefix in json_response:
                network_view_ranges = ranges.get(returned_prefix["network_view"], {})
                prefix_ranges = network_view_ranges.get(returned_prefix["network"])
                if prefix_ranges:
                    returned_prefix["ranges"] = prefix_ranges
        else:
            logger.info("Support for DHCP Ranges is not currently supported for IPv6 Networks.")
        return json_response

    def get_authoritative_zone(self, network_view: Optional[str] = None):
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
        if network_view:
            dns_view = self.get_default_dns_view_for_network_view(network_view)
            params["view"] = dns_view
        response = self._request("GET", url_path, params=params)
        logger.debug(response.json())
        return response.json().get("result")

    def _find_network_reference(self, network, network_view: Optional[str] = None):
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
        if network_view:
            params["network_view"] = network_view
        response = self._request("GET", url_path, params=params)
        logger.debug(response.json())
        return response.json()

    def find_next_available_ip(self, network, network_view: Optional[str] = None):
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
            network_ref_id = self._find_network_reference(network=network, network_view=network_view)
        except Exception as err:  # pylint: disable=broad-except
            # TODO: Add network-view to the error @progala
            logger.warning("Network reference not found for %s: %s", network, err)
            return next_ip_avail

        if network_ref_id and isinstance(network_ref_id, list):
            network_ref_id = network_ref_id[0].get("_ref")
            url_path = network_ref_id
            params = {"_function": "next_available_ip"}
            payload = {"num": 1}
            response = self._request("POST", url_path, params=params, json=payload)
            logger.debug(response.json())
            next_ip_avail = response.json().get("ips")[0]

        return next_ip_avail

    def reserve_fixed_address(self, network, mac_address, network_view: Optional[str] = None):
        """Reserve the next available ip address for a given network range.

        Returns:
            Str: The IP Address that was reserved

        Return Response:
            "10.220.0.1"
        """
        # Get the next available IP Address for this network
        ip_address = self.find_next_available_ip(network=network, network_view=network_view)
        if ip_address:
            url_path = "fixedaddress"
            params = {"_return_fields": "ipv4addr", "_return_as_object": 1}
            payload = {"ipv4addr": ip_address, "mac": mac_address}
            if network_view:
                payload["network_view"] = network_view
            response = self._request("POST", url_path, params=params, json=payload)
            logger.debug(response.json())
            return response.json().get("result").get("ipv4addr")
        return False

    def create_fixed_address(self, ip_address, mac_address, network_view: Optional[str] = None):
        """Create a fixed ip address within Infoblox.

        Returns:
            Str: The IP Address that was reserved

        Return Response:
            "10.220.0.1"
        """
        url_path = "fixedaddress"
        params = {"_return_fields": "ipv4addr", "_return_as_object": 1}
        payload = {"ipv4addr": ip_address, "mac": mac_address}
        if network_view:
            payload["network_view"] = network_view
        response = self._request("POST", url_path, params=params, json=payload)
        logger.debug(response.json())
        return response.json().get("result").get("ipv4addr")

    def create_host_record(self, fqdn, ip_address, network_view: Optional[str] = None):
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
        if network_view:
            payload["network_view"] = network_view
        try:
            response = self._request("POST", url_path, params=params, json=payload)
        except HTTPError as err:
            logger.info("Host record error: %s", err.response.text)
            return []
        logger.debug("Infoblox host record created: %s", response.json())
        return response.json().get("result")

    def delete_host_record(self, ip_address, network_view: Optional[str] = None):
        """Delete provided IP Address from Infoblox."""
        resource = self.get_host_record_by_ip(ip_address=ip_address, network_view=network_view)
        # TODO: Add network view to messages @progala
        if resource:
            ref = resource[0]["_ref"]
            self._delete(ref)
            response = {"deleted": ip_address}
        else:
            response = {"error": f"Did not find {ip_address}"}
        logger.debug(response)
        return response

    def create_ptr_record(self, fqdn, ip_address, network_view: Optional[str] = None):
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
        params = {"_return_fields": "name,ptrdname,ipv4addr,view", "_return_as_object": 1}
        reverse_host = str(reversename.from_address(ip_address))[
            0:-1
        ]  # infoblox does not accept the top most domain '.', so we strip it
        payload = {"name": reverse_host, "ptrdname": fqdn}  # , "ipv4addr": ip_address}
        if network_view:
            dns_view = self.get_default_dns_view_for_network_view(network_view)
            payload["view"] = dns_view
        response = self._request("POST", url_path, params=params, json=payload)
        # TODO: Add network view/dns view to the message @progala
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
        logger.debug(response.json())
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
        logger.debug(response.json())
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
        logger.debug(response.json())
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
        logger.debug(response.json())
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
        logger.debug(response.json())
        if len(response.json()):
            return response.json()[0]
        else:
            return []

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
        logger.debug(response.json())
        return response.json()

    @staticmethod
    def get_ipaddr_status(ip_record: dict) -> str:
        """Determine the IPAddress status based on the status key."""
        if "USED" in ip_record["status"]:
            return "Active"
        return "Reserved"

    @staticmethod
    def get_ipaddr_type(ip_record: dict) -> str:
        """Determine the IPAddress type based on the usage key."""
        if "DHCP" in ip_record["usage"]:
            return "dhcp"
        if "SLAAC" in ip_record["usage"]:
            return "slaac"
        return "host"

    def _find_matching_resources(self, resource, **params):
        """Find the resource for given parameters.

        Returns:
            str: _ref of an object

        Return Response:
            _ref: fixedaddress/ZG5zLmZpeGVkX2FkZHJlc3MkMTAuMjIwLjAuMy4wLi4:10.220.0.3/default
        """
        response = self._request("GET", resource, params=params)
        logger.debug(response.json())
        return response.json()

    # TODO: See if we should accept params dictionary and extended to both host record and fixed address
    # TODO: This doesn't work very well at all currently @progala
    # Perhaps make multiple searches, or go through types returned by the search
    def update_ipaddress(
        self, ip_address, network_view: Optional[str] = None, **data
    ):  # pylint: disable=inconsistent-return-statements
        """Update a IP Address object with a given ip address.

        Args:
            ip_address (str): Valid IP address
            data (dict): keyword args used to update the object e.g. comment="updateme"

        Returns:
            Dict: Dictionary of _ref and name

        Return Response:
        {
            "_ref": "fixedaddress/ZG5zLmZpeGVkX2FkZHJlc3MkMTAuMjIwLjAuMy4wLi4:10.220.0.3/default",
            "ipv4addr": "10.220.0.3"
        }
        """
        # resources = self._find_matching_resources("search", search_string=ip_address, objtype="fixedaddress")
        # resources.extend(self._find_matching_resources("search", search_string=ip_address, objtype="record:host"))
        resources = self._find_matching_resources("search", address=ip_address)
        if not resources:
            return
        found_ipv4_ref = None
        # We can get multiple resources of varying types. The name of resource is embedded in the `_ref` attr
        resource_types = ["fixedaddress"]
        if network_view:
            for resource in resources:
                ref = resource.get("_ref")
                if ref.split("/")[0] not in resource_types:
                    continue
                if resource.get("network_view") != network_view:
                    continue
                if resource.get("ipv4addr") != ip_address:
                    continue
                found_ipv4_ref = ref
                break
        else:
            for resource in resources:
                ref = resource.get("_ref")
                if ref.split("/")[0] not in resource_types:
                    continue
                if resource.get("ipv4addr") != ip_address:
                    continue
                found_ipv4_ref = ref
                break

        if not found_ipv4_ref:
            return
        # params = {"_return_fields": "ipv4addr", "_return_as_object": 1}
        params = {}
        try:
            logger.debug(data)
            response = self._request("PUT", path=found_ipv4_ref, params=params, json=data)
        except HTTPError as err:
            logger.info("Resource: %s", found_ipv4_ref)
            logger.info("Could not update IP address: %s", err.response.text)
            return
        logger.info("Infoblox IP Address updated: %s", response.json())
        return response.json()

    def get_tree_from_container(self, root_container: str, network_view: Optional[str] = None) -> list:
        """Returns the list of all child containers from a given root container."""
        flattened_tree = []
        stack = []
        root_containers = self.get_network_containers(prefix=root_container)
        if network_view:
            root_containers = self.get_network_containers(prefix=root_container, network_view=network_view)
        else:
            root_containers = self.get_network_containers(prefix=root_container)
        if root_containers:
            stack = [root_containers[0]]

        get_child_network_containers_kwargs = {}
        if network_view:
            get_child_network_containers_kwargs["network_view"] = network_view

        while stack:
            current_node = stack.pop()
            get_child_network_containers_kwargs.update({"prefix": current_node["network"]})
            flattened_tree.append(current_node)
            children = self.get_child_network_containers(**get_child_network_containers_kwargs)
            stack.extend(children)

        return flattened_tree

    def remove_duplicates(self, network_list: list) -> list:
        """Removes duplicate networks from a list of networks."""
        seen_networks = set()
        new_list = []
        for network in network_list:
            if network["network"] not in seen_networks:
                new_list.append(network)
                seen_networks.add(network["network"])

        return new_list

    def get_network_containers(self, prefix: str = "", ipv6: bool = False, network_view: Optional[str] = None):
        """Get all Network Containers.

        Args:
            prefix (str): Specific prefix (192.168.0.1/24)
            ipv6 (bool): Whether the call should be made for IPv6 network containers.

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
        if ipv6:
            url_path = "ipv6networkcontainer"
        else:
            url_path = "networkcontainer"

        params = {
            "_return_as_object": 1,
            "_return_fields": "network,comment,network_view,extattrs,rir_organization,rir",
            "_max_results": 100000,
        }
        if network_view:
            params.update({"network_view": network_view})
        if prefix:
            params.update({"network": prefix})
        response = self._request("GET", url_path, params=params)
        response = response.json()
        logger.debug(response)
        results = response.get("result", [])
        for res in results:
            res.update({"status": "container"})
        return results

    def get_child_network_containers(self, prefix: str, network_view: Optional[str] = None):
        """Get all Child Network Containers for Container.

        Returns:
            (list) of record dicts

        Return Response:
        [
            {
                "_ref": "networkcontainer/ZG5zLm5ldHdvcmtfY29udGFpbmVyJDE5Mi4xNjguMi4wLzI0LzA:192.168.2.0/23/default",
                "comment": "Campus LAN",
                "extattrs": {},
                "network": "192.168.2.0/24",
                "network_view": "default",
                "rir": "NONE",
            },
            {
                "_ref": "networkcontainer/ZG5zLm5ldHdvcmtfY29udGFpbmVyJDE5Mi4xNjguMi4wLzI0LzA:192.168.2.0/23/default",
                "comment": "Campus LAN 2",
                "extattrs": {},
                "network": "192.168.3.0/24",
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
        if network_view:
            params.update({"network_view": network_view})
        params.update({"network_container": prefix})
        response = self._request("GET", url_path, params=params)
        response = response.json()
        logger.debug(response)
        results = response.get("result", [])
        for res in results:
            res.update({"status": "container"})
        return results

    def get_child_subnets_from_container(self, prefix: str, network_view: Optional[str] = None):
        """Get child subnets from container.

        Args:
            prefix (str): Network prefix - '10.220.0.0/22'

        Returns:
            (list) of record dicts

        Return Response:
        [
            {
                "_ref": "network/ZG5zLm5ldHdvcmskMTAuMjIzLjAuMC8yMS8w:10.220.0.0/24/default",
                "comment": "Campus 1",
                "extattrs": {},
                "network": "10.220.0.0/24",
                "network_view": "default",
                "rir": "NONE",
                "vlans": [],
            },
            {
                "_ref": "network/ZG5zLm5ldHdvcmskMTAuMjIzLjAuMC8yMS8w:10.220.1.0/24/default",
                "comment": "Campus 2",
                "extattrs": {},
                "network": "10.220.1.0/24",
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
        if network_view:
            params.update({"network_view": network_view})
        params.update({"network_container": prefix})

        try:
            response = self._request("GET", url_path, params=params)
        except HTTPError as err:
            logger.info(err.response.text)
            return []
        response = response.json()
        logger.debug(response)
        return response.get("result")

    def get_network_views(self):
        """Get all network views.

        Returns:
            (list) of record dicts

        Return Response:
        [
          {
            "_ref": "networkview/ZG5zLm5ldHdvcmtfdmlldyQw:default/true",
            "associated_dns_views": [
              "default"
            ],
            "extattrs": {

            },
            "is_default": true,
            "name": "default"
          },
          {
            "_ref": "networkview/ZG5zLm5ldHdvcmtfdmlldyQx:prod/false",
            "associated_dns_views": [
              "default.prod"
            ],
            "extattrs": {

            },
            "is_default": false,
            "name": "prod"
          },
          {
            "_ref": "networkview/ZG5zLm5ldHdvcmtfdmlldyQy:dev/false",
            "associated_dns_views": [
              "default.dev"
            ],
            "extattrs": {

            },
            "is_default": false,
            "name": "dev"
          }
        ]
        """
        url_path = "networkview"
        params = {
            "_return_fields": "name,associated_dns_views,extattrs,comment,is_default",
        }
        try:
            response = self._request("GET", url_path, params=params)
        except HTTPError as err:
            logger.info(err.response.text)
            return []
        logger.debug(response.json())
        return response.json()

    def get_network_view(self, name: str):
        """Get network view object for given name.

        Args:
            name (str): Name of the network view - 'dev'

        Returns:
            (dict) record dict

        Return Response:
        [
            {
              "_ref": "networkview/ZG5zLm5ldHdvcmtfdmlldyQy:dev/false",
              "associated_dns_views": [
                "default.dev"
              ],
              "extattrs": {

              },
              "is_default": false,
              "name": "dev"
            }
        ]
        """
        url_path = "networkview"
        params = {
            "name": name,
            "_return_fields": "name,associated_dns_views,extattrs,comment,is_default",
        }
        try:
            response = self._request("GET", path=url_path, params=params)
        except HTTPError as err:
            logger.info(err.response.text)
            return []
        logger.debug(response.json())
        return response.json()

    def get_default_dns_view_for_network_view(self, network_view: str):
        """Get default (first on the list) DNS view for given network view.

        Args:
            network_view (str): Name of the network view - 'dev'

        Returns:
            (str) name of the default dns view
        """
        _network_view = self.get_network_view(network_view)
        logger.info(_network_view)
        if _network_view:
            return _network_view[0]["associated_dns_views"][0]
        else:
            return None
