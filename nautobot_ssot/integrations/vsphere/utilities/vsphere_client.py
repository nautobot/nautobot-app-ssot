"""Extending vSphere SDK."""

import logging
import re
import urllib.parse
from dataclasses import dataclass
from typing import Dict

import requests
import urllib3
from requests.auth import HTTPBasicAuth

from nautobot_ssot.exceptions import InvalidUrlScheme

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


@dataclass
class VsphereConfig:  # pylint: disable=too-many-instance-attributes
    """Configuration for vSphere Client."""

    vsphere_uri: str
    username: str
    password: str
    verify_ssl: bool
    vm_status_map: dict
    ip_status_map: dict
    vm_interface_map: dict
    primary_ip_sort_by: str
    ignore_link_local: bool
    use_clusters: bool
    sync_tagged_only: bool
    debug: bool


class VsphereClient:  # pylint: disable=too-many-instance-attributes
    """Class for interacting with VMWare vSphere."""

    def __init__(self, config: VsphereConfig):  # pylint: disable=W0235, R0913
        """Initialize vSphere Client class."""
        self.config = config
        self.vsphere_uri = self._parse_vsphere_uri(config.vsphere_uri)
        self.auth = HTTPBasicAuth(config.username, config.password)
        self.session = self._init_session()
        self._authenticate()

    def _parse_vsphere_uri(self, uri: str) -> str:
        parsed = parse_url(uri.strip())
        if parsed.scheme not in ("http", "https"):
            raise InvalidUrlScheme(parsed.scheme)
        return parsed._replace(scheme="https").geturl()

    def _init_session(self) -> requests.Session:
        if not self.config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        session = requests.Session()
        session.verify = self.config.verify_ssl
        session.headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        return session

    def _authenticate(self):
        response = self.session.post(f"{self.vsphere_uri}/rest/com/vmware/cis/session", auth=self.auth)
        self.rest_client = response
        session_token = response.json().get("value")
        self.session.headers.update({"vmware-api-session-id": session_token})
        if response.status_code == 200:
            LOGGER.debug("vSphere Client authenticated and session established successfully.")
            self.is_authenticated = True
        else:
            LOGGER.error("Failed to authenticate vSphere Client. Status code: %s", response.status_code)
            self.is_authenticated = False

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
