"""Thin :mod:`proxmoxer` wrapper for reading from the Proxmox VE REST API with an API token."""

import logging
import re
import urllib.parse
from dataclasses import dataclass

import urllib3
from proxmoxer import ProxmoxAPI
from proxmoxer.core import ResourceException

from nautobot_ssot.exceptions import InvalidUrlScheme

LOGGER = logging.getLogger(__name__)


def parse_url(address):
    """Parse a URL, defaulting the scheme to ``https`` if none is given.

    Args:
        address (str): URL set by the end user for the Proxmox VE instance.

    Returns:
        ParseResult: The parsed results from urllib.
    """
    if not re.search(r"^[A-Za-z0-9+.\-]+://", address):
        address = f"https://{address}"
    return urllib.parse.urlparse(address)


@dataclass
class ProxmoxConfig:  # pylint: disable=too-many-instance-attributes
    """Configuration for the Proxmox VE Client."""

    proxmox_uri: str
    token_id: str
    token_secret: str
    verify_ssl: bool
    vm_status_map: dict
    ip_status_map: dict
    primary_ip_sort_by: str
    ignore_link_local: bool
    use_clusters: bool
    sync_lxc: bool
    sync_nodes_as_devices: bool
    sync_proxmox_tags: bool
    debug: bool


class ProxmoxClient:
    """Class for interacting with Proxmox VE via the proxmoxer library."""

    def __init__(self, config: ProxmoxConfig):
        """Initialize the client and authenticate with an API token.

        Args:
            config (ProxmoxConfig): Connection and sync settings.
        """
        self.config = config
        self.is_authenticated = False
        parsed = self._parse_proxmox_uri(config.proxmox_uri)
        self.host = parsed.netloc or parsed.path
        # Token IDs look like ``user@realm!tokenid``; proxmoxer takes the user and token name separately.
        user, _, token_name = config.token_id.partition("!")
        self.user = user
        self.token_name = token_name

        if not self.config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self.api = ProxmoxAPI(
            self.host,
            user=user,
            token_name=token_name,
            token_value=config.token_secret,
            verify_ssl=config.verify_ssl,
            service="PVE",
        )
        self._authenticate()

    def _parse_proxmox_uri(self, uri: str):
        """Validate and normalize the configured Proxmox VE URI.

        Args:
            uri (str): The configured URI.

        Returns:
            ParseResult: The parsed URI.

        Raises:
            InvalidUrlScheme: If the scheme is not ``http`` or ``https``.
        """
        parsed = parse_url(uri.strip())
        if parsed.scheme not in ("http", "https"):
            raise InvalidUrlScheme(parsed.scheme)
        return parsed

    def _authenticate(self):
        """Verify the API token works by issuing a lightweight request."""
        try:
            self.api.version.get()
            self.is_authenticated = True
            LOGGER.debug("Proxmox VE client authenticated successfully.")
        except (ResourceException, OSError) as err:
            self.is_authenticated = False
            LOGGER.error("Failed to authenticate Proxmox VE client: %s", err)

    def get_cluster_status(self):
        """Return ``/cluster/status`` entries.

        Standalone hosts return only ``node`` entries, with no ``cluster`` entry.

        Returns:
            list: The cluster and node status entries.
        """
        return self.api.cluster.status.get()

    def get_resources(self, resource_type=None):
        """Return the ``/cluster/resources`` inventory.

        Args:
            resource_type (Optional[str]): Resource type to filter by, e.g. ``"vm"``.

        Returns:
            list: The resource entries.
        """
        if resource_type:
            return self.api.cluster.resources.get(type=resource_type)
        return self.api.cluster.resources.get()

    def get_nodes(self):
        """Return the list of nodes from ``/nodes``.

        Returns:
            list: The node entries.
        """
        return self.api.nodes.get()

    def get_node_network(self, node):
        """Return a node's interface configuration from ``/nodes/{node}/network``.

        Args:
            node (str): The node name.

        Returns:
            list: The interface entries, or an empty list if the endpoint is unavailable.
        """
        try:
            return self.api.nodes(node).network.get()
        except (ResourceException, OSError) as err:
            LOGGER.debug("Unable to read network config for node %s: %s", node, err)
            return []

    def get_node_status(self, node):
        """Return node hardware and version details from ``/nodes/{node}/status``.

        Args:
            node (str): The node name.

        Returns:
            dict: The node status, or an empty dict if the endpoint is unavailable.
        """
        try:
            return self.api.nodes(node).status.get()
        except (ResourceException, OSError) as err:
            LOGGER.debug("Unable to read status for node %s: %s", node, err)
            return {}

    def get_qemu_config(self, node, vmid):
        """Return a QEMU VM's configuration.

        Args:
            node (str): The node name.
            vmid (int): The VM ID.

        Returns:
            dict: The VM configuration.
        """
        return self.api.nodes(node).qemu(vmid).config.get()

    def get_lxc_config(self, node, vmid):
        """Return an LXC container's configuration.

        Args:
            node (str): The node name.
            vmid (int): The container ID.

        Returns:
            dict: The container configuration.
        """
        return self.api.nodes(node).lxc(vmid).config.get()

    def get_qemu_agent_interfaces(self, node, vmid):
        """Return a QEMU VM's network interfaces as reported by the guest agent.

        Requires the VM to be running with the guest agent installed.

        Args:
            node (str): The node name.
            vmid (int): The VM ID.

        Returns:
            list: The agent's interface entries, or an empty list if the agent is unavailable.
        """
        try:
            result = self.api.nodes(node).qemu(vmid).agent("network-get-interfaces").get()
        except (ResourceException, OSError) as err:
            LOGGER.debug("Guest agent unavailable for VM %s on node %s: %s", vmid, node, err)
            return []
        return result.get("result", []) if isinstance(result, dict) else []
