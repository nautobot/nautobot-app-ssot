"""Unit tests for the Proxmox VE API client."""

import unittest
from unittest.mock import MagicMock, patch

from nautobot_ssot.integrations.proxmox.utilities.proxmox_client import ProxmoxClient, ProxmoxConfig


def _config(token_id="svc@pve!nautobot"):
    """Build a ProxmoxConfig for client tests."""
    return ProxmoxConfig(  # nosec
        proxmox_uri="https://pve.local:8006",
        token_id=token_id,
        token_secret="00000000-0000-0000-0000-000000000000",
        verify_ssl=False,
        vm_status_map={"running": "Active", "stopped": "Offline"},
        ip_status_map={"PREFERRED": "Active", "UNKNOWN": "Reserved"},
        primary_ip_sort_by="Lowest",
        ignore_link_local=True,
        use_clusters=True,
        sync_lxc=True,
        sync_nodes_as_devices=True,
        sync_proxmox_tags=True,
        debug=False,
    )


@patch("nautobot_ssot.integrations.proxmox.utilities.proxmox_client.ProxmoxAPI")
class TestProxmoxClient(unittest.TestCase):
    """Test cases for ProxmoxClient."""

    def test_token_id_parsing(self, mock_api):
        """The API Token ID is split into user and token name for proxmoxer."""
        client = ProxmoxClient(_config(token_id="svc@pve!nautobot"))
        self.assertEqual(client.user, "svc@pve")
        self.assertEqual(client.token_name, "nautobot")
        _, kwargs = mock_api.call_args
        self.assertEqual(kwargs["user"], "svc@pve")
        self.assertEqual(kwargs["token_name"], "nautobot")
        self.assertEqual(kwargs["token_value"], "00000000-0000-0000-0000-000000000000")

    def test_authentication_success(self, mock_api):
        """is_authenticated is True when the version probe succeeds."""
        client = ProxmoxClient(_config())
        self.assertTrue(client.is_authenticated)
        mock_api.return_value.version.get.assert_called_once()

    def test_authentication_failure(self, mock_api):
        """is_authenticated is False when the version probe raises."""
        mock_api.return_value.version.get.side_effect = OSError("connection refused")
        client = ProxmoxClient(_config())
        self.assertFalse(client.is_authenticated)

    def test_get_qemu_agent_interfaces_returns_result(self, mock_api):
        """The guest-agent result list is unwrapped from the response dict."""
        client = ProxmoxClient(_config())
        agent_chain = mock_api.return_value.nodes.return_value.qemu.return_value.agent.return_value
        agent_chain.get.return_value = {"result": [{"name": "eth0"}]}
        self.assertEqual(client.get_qemu_agent_interfaces("pve1", 100), [{"name": "eth0"}])

    def test_get_qemu_agent_interfaces_swallows_errors(self, mock_api):
        """Guest-agent failures return an empty list instead of raising."""
        client = ProxmoxClient(_config())
        agent_chain = mock_api.return_value.nodes.return_value.qemu.return_value.agent.return_value
        agent_chain.get.side_effect = OSError("agent not running")
        self.assertEqual(client.get_qemu_agent_interfaces("pve1", 100), [])

    def test_get_node_network_swallows_errors(self, mock_api):
        """Network read failures return an empty list instead of raising."""
        client = ProxmoxClient(_config())
        mock_api.return_value.nodes.return_value.network.get.side_effect = OSError("boom")
        self.assertEqual(client.get_node_network("pve1"), [])

    def test_get_node_status_swallows_errors(self, mock_api):
        """Status read failures return an empty dict instead of raising."""
        client = ProxmoxClient(_config())
        mock_api.return_value.nodes.return_value.status.get.side_effect = OSError("boom")
        self.assertEqual(client.get_node_status("pve1"), {})

    def test_passthrough_calls(self, mock_api):
        """Cluster/resource/node reads delegate to the proxmoxer client."""
        client = ProxmoxClient(_config())
        mock_api.return_value.cluster.resources.get.return_value = [{"vmid": 100}]
        self.assertEqual(client.get_resources(resource_type="vm"), [{"vmid": 100}])
        mock_api.return_value.cluster.resources.get.assert_called_with(type="vm")
        self.assertIsInstance(client.api, MagicMock)
