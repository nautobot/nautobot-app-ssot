"""Client for interacting with the Proxmox VE REST API.

This is a thin wrapper around :mod:`proxmoxer` that handles API-token authentication and
exposes the read endpoints needed by the SSoT source adapter.
"""

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
    """Handle the case where the protocol isn't included in the URL address.

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
        """Initialize the Proxmox VE client and authenticate using an API token."""
        self.config = config
        self.is_authenticated = False
        parsed = self._parse_proxmox_uri(config.proxmox_uri)
        self.host = parsed.netloc or parsed.path
        # An API Token ID has the form ``user@realm!tokenid``; proxmoxer wants the user and token
        # name separately, with the token secret (a UUID) passed as ``token_value``.
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
        """Validate and normalize the configured Proxmox VE URI."""
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
        """Return cluster status entries (``type`` of ``cluster`` or ``node``).

        On standalone hosts (no cluster configured) this typically returns only node entries.
        """
        return self.api.cluster.status.get()

    def get_resources(self, resource_type=None):
        """Return the flattened ``/cluster/resources`` inventory, optionally filtered by type."""
        if resource_type:
            return self.api.cluster.resources.get(type=resource_type)
        return self.api.cluster.resources.get()

    def get_nodes(self):
        """Return the list of nodes from ``/nodes``."""
        return self.api.nodes.get()

    def get_node_network(self, node):
        """Return the network interface configuration for a node from ``/nodes/{node}/network``.

        Returns an empty list if the endpoint is unavailable rather than raising.
        """
        try:
            return self.api.nodes(node).network.get()
        except (ResourceException, OSError) as err:
            LOGGER.debug("Unable to read network config for node %s: %s", node, err)
            return []

    def get_node_status(self, node):
        """Return node hardware/version detail from ``/nodes/{node}/status``.

        Returns an empty dict if the endpoint is unavailable rather than raising.
        """
        try:
            return self.api.nodes(node).status.get()
        except (ResourceException, OSError) as err:
            LOGGER.debug("Unable to read status for node %s: %s", node, err)
            return {}

    def get_qemu_config(self, node, vmid):
        """Return the QEMU VM configuration for the given node and vmid."""
        return self.api.nodes(node).qemu(vmid).config.get()

    def get_lxc_config(self, node, vmid):
        """Return the LXC container configuration for the given node and vmid."""
        return self.api.nodes(node).lxc(vmid).config.get()

    def get_qemu_agent_interfaces(self, node, vmid):
        """Return guest-agent network interfaces for a QEMU VM.

        Requires the QEMU guest agent to be installed and running and the VM to be powered on.
        Returns an empty list when the agent is unavailable rather than raising.
        """
        try:
            result = self.api.nodes(node).qemu(vmid).agent("network-get-interfaces").get()
        except (ResourceException, OSError) as err:
            LOGGER.debug("Guest agent unavailable for VM %s on node %s: %s", vmid, node, err)
            return []
        return result.get("result", []) if isinstance(result, dict) else []
