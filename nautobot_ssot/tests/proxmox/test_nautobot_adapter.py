"""Tests for the Nautobot-side adapter (NBAdapter) of the Proxmox VE integration."""

from nautobot.apps.testing import TestCase

from .proxmox_fixtures import (
    ProxmoxSyncTestMixin,
    _get_device_interface_dict,
    _get_node_device_dict,
    _get_virtual_machine_dict,
)


class TestProxmoxNautobotAdapter(ProxmoxSyncTestMixin, TestCase):
    """Tests for loading existing Proxmox-synced objects back into DiffSync."""

    def setUp(self):
        """Sync a node, a node interface and a VM into Nautobot."""
        super().setUp()
        source = self._source()
        self._seed_cluster(source)
        device = source.device(**_get_node_device_dict({"name": "pve1"}))
        interface = source.device_interface(
            **_get_device_interface_dict({"name": "eth0", "device__name": "pve1", "mtu": 1500})
        )
        vm = source.virtual_machine(**_get_virtual_machine_dict({"name": "web01"}))
        source.add(device)
        source.add(interface)
        source.add(vm)
        device.add_child(interface)

        source.sync_to(self._nb_adapter())

    def test_load_reads_existing_objects(self):
        """NBAdapter.load() loads the previously synced objects into the DiffSync store."""
        nb_adapter = self._nb_adapter()

        device = nb_adapter.get(nb_adapter.device, {"name": "pve1"})
        self.assertEqual(device.name, "pve1")
        vm = nb_adapter.get(nb_adapter.virtual_machine, {"name": "web01", "cluster__name": "TestCluster"})
        self.assertEqual(vm.name, "web01")
        interface = nb_adapter.get(nb_adapter.device_interface, {"name": "eth0", "device__name": "pve1"})
        self.assertEqual(interface.mtu, 1500)

    def test_sync_complete_is_noop_without_deferred_items(self):
        """sync_complete handles empty deferred queues without error."""
        nb_adapter = self._nb_adapter()
        nb_adapter.sync_complete(source=None, diff=None)
