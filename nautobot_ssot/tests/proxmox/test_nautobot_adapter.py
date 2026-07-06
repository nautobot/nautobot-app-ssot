# pylint: disable=R0801
"""Tests for the Nautobot-side adapter (NBAdapter) of the Proxmox VE integration."""

from unittest.mock import MagicMock

from django.apps import apps as django_apps
from nautobot.apps.testing import TestCase

from nautobot_ssot.integrations.proxmox.constants import SSOT_TAG_DESCRIPTION, SSOT_TAG_NAME
from nautobot_ssot.integrations.proxmox.diffsync.adapters.adapter_nautobot import NBAdapter
from nautobot_ssot.integrations.proxmox.diffsync.adapters.adapter_proxmox import ProxmoxDiffSync
from nautobot_ssot.integrations.proxmox.signals import nautobot_database_ready_callback

from .proxmox_fixtures import _get_device_interface_dict, _get_virtual_machine_dict, create_default_proxmox_config


class TestProxmoxNautobotAdapter(TestCase):
    """Tests for loading existing Proxmox-synced objects back into DiffSync."""

    def setUp(self):
        """Seed scaffolding and create a small synced inventory to load back."""
        nautobot_database_ready_callback(sender=None, apps=django_apps)
        self.config = create_default_proxmox_config()

        source = ProxmoxDiffSync(
            job=MagicMock(), sync=MagicMock(), client=MagicMock(), config=self.config, cluster_filters=None
        )
        source.add(source.tag(name=SSOT_TAG_NAME, description=SSOT_TAG_DESCRIPTION))
        clustergroup = source.clustergroup(name="TestClusterGroup")
        cluster = source.cluster(
            name="TestCluster", cluster_type__name="Proxmox VE", cluster_group__name="TestClusterGroup"
        )
        source.add(clustergroup)
        source.add(cluster)
        clustergroup.add_child(cluster)
        device = source.device(
            name="pve1",
            device_type__model="Proxmox Node",
            role__name="Proxmox Node",
            location__name="Proxmox VE Default Location",
            status__name="Active",
            clusters=[{"name": "TestCluster"}],
        )
        interface = source.device_interface(
            **_get_device_interface_dict({"name": "eth0", "device__name": "pve1", "mtu": 1500})
        )
        vm = source.virtual_machine(**_get_virtual_machine_dict({"name": "web01"}))
        source.add(device)
        source.add(interface)
        source.add(vm)
        device.add_child(interface)

        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()
        source.sync_to(nb_adapter)

    def test_load_reads_existing_objects(self):
        """NBAdapter.load() loads the previously synced objects into the DiffSync store."""
        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()

        device = nb_adapter.get(nb_adapter.device, {"name": "pve1"})
        self.assertEqual(device.name, "pve1")
        vm = nb_adapter.get(nb_adapter.virtual_machine, {"name": "web01", "cluster__name": "TestCluster"})
        self.assertEqual(vm.name, "web01")
        interface = nb_adapter.get(nb_adapter.device_interface, {"name": "eth0", "device__name": "pve1"})
        self.assertEqual(interface.mtu, 1500)

    def test_sync_complete_is_noop_without_deferred_items(self):
        """sync_complete handles empty deferred queues without error."""
        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()
        # Should not raise with empty _primary_ips / _device_primary_ips / _interface_links.
        nb_adapter.sync_complete(source=None, diff=None)
