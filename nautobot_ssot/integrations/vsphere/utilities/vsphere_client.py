"""Extending vSphere SDK."""

import logging
import re
import urllib.parse
from typing import Dict

import requests
from requests.auth import HTTPBasicAuth

LOGGER = logging.getLogger(__name__)


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


class InvalidUrlScheme(Exception):
    """Exception raised for wrong scheme being passed for URL.

    Attributes:
        message (str): Returned explanation of Error.
    """

    def __init__(self, scheme):
        """Initialize Exception with wrong scheme in message."""
        self.message = f"Invalid URL scheme '{scheme}' found for vSphere URL. Please correct to use HTTPS."
        super().__init__(self.message)


class VsphereClient:  # pylint: disable=too-many-instance-attributes
    """Class for interacting with VMWare vSphere."""

    def __init__(
        self,
        vsphere_uri,
        username,
        password,
        verify_ssl,
        vm_status_map,
        ip_status_map,
        vm_interface_map,
        primary_ip_sort_by,
        ignore_link_local,
        debug,
    ):  # pylint: disable=W0235, R0913
        """Initialize vSphere Client class."""
        parsed_url = parse_url(vsphere_uri.strip())
        if parsed_url.scheme != "https":
            if parsed_url.scheme == "http":
                self.vsphere_uri = parsed_url._replace(scheme="https").geturl()
            else:
                raise InvalidUrlScheme(scheme=parsed_url.scheme)
        else:
            self.vsphere_uri = parsed_url.geturl()

        self.auth = HTTPBasicAuth(username, password)
        self.session = self._init_session(verify_ssl=verify_ssl)
        self.rest_client = self.session.post(f"{self.vsphere_uri}/rest/com/vmware/cis/session", auth=self.auth)
        LOGGER.debug("vSphere Client authenticated and session established.")

        self.vm_status_map = vm_status_map
        self.ip_status_map = ip_status_map
        self.vm_interface_map = vm_interface_map
        self.primary_ip_sort_by = primary_ip_sort_by
        self.ignore_link_local = ignore_link_local
        self.debug = debug

    def _init_session(self, verify_ssl):
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
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        session = requests.Session()
        session.verify = verify_ssl
        session.headers.update(self.headers)

        return session

    def _request(self, method: str, path: str, **kwargs):
        """Return a response object after making a request to by other methods.

        Args:
            method (str): Request method to call in self.session.
            path (str): uri path to call.

        Returns:
            :class:`~requests.Response`: Response from the API.
        """
        url = requests.compat.urljoin(self.vsphere_uri, path)
        return self.session.request(method, url, **kwargs)

    def get_vms(self) -> Dict:
        """Get VMs."""
        return self._request("GET", f"{self.vsphere_uri}/rest/vcenter/vm")

    def get_vms_from_cluster(self, cluster: str) -> Dict:
        """Get VMs."""
        return self._request("GET", f"{self.vsphere_uri}/rest/vcenter/vm?filter.clusters={cluster}")

    def get_vms_from_dc(self, datacenter: str) -> Dict:
        """Get VMs."""
        return self._request("GET", f"{self.vsphere_uri}/rest/vcenter/vm?filter.datacenters={datacenter}")

    def get_datacenters(self) -> Dict:
        """Get datacenters."""
        return self._request("GET", f"{self.vsphere_uri}/rest/vcenter/datacenter")

    def get_datacenter_details(self, datacenter: str) -> Dict:
        """Get datacenters."""
        return self._request("GET", f"{self.vsphere_uri}/rest/vcenter/datacenter/{datacenter}")

    def get_clusters(self) -> Dict:
        """Get Clusters."""
        return self._request("GET", f"{self.vsphere_uri}/rest/vcenter/cluster")

    def get_clusters_from_dc(self, datacenter: str) -> Dict:
        """Get Clusters."""
        return self._request(
            "GET",
            f"{self.vsphere_uri}/rest/vcenter/cluster?filter.datacenters={datacenter}",
        )

    def get_cluster_details(self, cluster_name: str) -> Dict:
        """Get Clusters."""
        return self._request("GET", f"{self.vsphere_uri}/rest/vcenter/cluster/{cluster_name}")

    def get_vm_details(self, vm_id: str) -> Dict:
        """Get all VMs details."""
        return self._request("GET", f"{self.vsphere_uri}/rest/vcenter/vm/{vm_id}")

    def get_host_from_cluster(self, cluster: str) -> Dict:
        """Get hosts from cluster."""
        return self._request("GET", f"{self.vsphere_uri}/rest/vcenter/host/?filter.clusters={cluster}")

    def get_host_details(self, host: str) -> Dict:
        """Get host details."""
        return self._request("GET", f"{self.vsphere_uri}/rest/vcenter/host/?filter.hosts={host}")

    def get_vm_interfaces(self, vm_id: str) -> Dict:
        """Get all VM interfaces."""
        return self._request(
            "GET",
            f"{self.vsphere_uri}/rest/vcenter/vm/{vm_id}/guest/networking/interfaces",
        )
