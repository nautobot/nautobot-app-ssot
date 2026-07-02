# pylint: disable=R0801
"""Update-path tests for the Proxmox VE DiffSync models (DB-backed)."""

from unittest.mock import MagicMock

from django.apps import apps as django_apps
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Interface
from nautobot.virtualization.models import VirtualMachine

from nautobot_ssot.integrations.proxmox.constants import SSOT_TAG_DESCRIPTION, SSOT_TAG_NAME
from nautobot_ssot.integrations.proxmox.diffsync.adapters.adapter_nautobot import NBAdapter
from nautobot_ssot.integrations.proxmox.diffsync.adapters.adapter_proxmox import ProxmoxDiffSync
from nautobot_ssot.integrations.proxmox.signals import nautobot_database_ready_callback

from .fixtures_proxmox import _get_device_interface_dict, _get_virtual_machine_dict, create_default_proxmox_config


class TestProxmoxDiffSyncModelsUpdate(TestCase):
    """Update-path tests: sync, then re-sync changed source models and assert ORM updates."""

    def setUp(self):
        """Build scaffolding + config."""
        nautobot_database_ready_callback(sender=None, apps=django_apps)
        self.config = create_default_proxmox_config()

    def _source(self):
        return ProxmoxDiffSync(
            job=MagicMock(), sync=MagicMock(), client=MagicMock(), config=self.config, cluster_filters=None
        )

    def _nb_adapter(self):
        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()
        return nb_adapter

    def _seed_cluster(self, source):
        source.add(source.tag(name=SSOT_TAG_NAME, description=SSOT_TAG_DESCRIPTION))
        clustergroup = source.clustergroup(name="TestClusterGroup")
        cluster = source.cluster(
            name="TestCluster", cluster_type__name="Proxmox VE", cluster_group__name="TestClusterGroup"
        )
        source.add(clustergroup)
        source.add(cluster)
        clustergroup.add_child(cluster)

    def test_virtual_machine_update(self):
        """Changing a VM's resources updates the Nautobot VirtualMachine."""
        source = self._source()
        self._seed_cluster(source)
        source.add(source.virtual_machine(**_get_virtual_machine_dict({"name": "web01", "memory": 4096})))
        source.sync_to(self._nb_adapter())
        self.assertEqual(VirtualMachine.objects.get(name="web01").memory, 4096)

        source2 = self._source()
        self._seed_cluster(source2)
        source2.add(source2.virtual_machine(**_get_virtual_machine_dict({"name": "web01", "memory": 8192})))
        source2.sync_to(self._nb_adapter())

        self.assertEqual(VirtualMachine.objects.get(name="web01").memory, 8192)

    def test_device_interface_update(self):
        """Changing a node interface's MTU updates the Nautobot Interface."""
        source = self._source()
        self._seed_cluster(source)
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
        source.add(device)
        source.add(interface)
        device.add_child(interface)
        source.sync_to(self._nb_adapter())
        self.assertEqual(Interface.objects.get(device__name="pve1", name="eth0").mtu, 1500)

        source2 = self._source()
        self._seed_cluster(source2)
        device2 = source2.device(
            name="pve1",
            device_type__model="Proxmox Node",
            role__name="Proxmox Node",
            location__name="Proxmox VE Default Location",
            status__name="Active",
            clusters=[{"name": "TestCluster"}],
        )
        interface2 = source2.device_interface(
            **_get_device_interface_dict({"name": "eth0", "device__name": "pve1", "mtu": 9000})
        )
        source2.add(device2)
        source2.add(interface2)
        device2.add_child(interface2)
        source2.sync_to(self._nb_adapter())

        self.assertEqual(Interface.objects.get(device__name="pve1", name="eth0").mtu, 9000)
        self.assertIn(SSOT_TAG_NAME, [tag.name for tag in Interface.objects.get(name="eth0").device.tags.all()])
