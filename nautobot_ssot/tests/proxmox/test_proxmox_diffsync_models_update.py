# pylint: disable=R0801
"""Update-path tests for the Proxmox VE DiffSync models (DB-backed)."""

from unittest.mock import MagicMock

from django.apps import apps as django_apps
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Interface
from nautobot.extras.models import Tag
from nautobot.virtualization.models import VirtualMachine

from nautobot_ssot.integrations.proxmox.constants import SSOT_TAG_DESCRIPTION, SSOT_TAG_NAME
from nautobot_ssot.integrations.proxmox.diffsync.adapters.adapter_nautobot import NBAdapter
from nautobot_ssot.integrations.proxmox.diffsync.adapters.adapter_proxmox import ProxmoxDiffSync
from nautobot_ssot.integrations.proxmox.signals import nautobot_database_ready_callback

from .proxmox_fixtures import (
    _get_device_interface_dict,
    _get_virtual_machine_dict,
    _get_vm_interface_dict,
    create_default_proxmox_config,
)


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

    def test_update_virtual_machine_primary_ip(self):
        """Changing a VM's primary IPv4 to a different existing IP updates the Nautobot VirtualMachine."""
        source = self._source()
        self._seed_cluster(source)
        vm = source.virtual_machine(**_get_virtual_machine_dict({"name": "web01", "primary_ip4__host": "10.0.10.50"}))
        interface = source.interface(**_get_vm_interface_dict({"name": "net0", "virtual_machine__name": "web01"}))
        ip_address = source.ip_address(
            host="10.0.10.50",
            mask_length=24,
            status__name="Active",
            vm_interfaces=[{"name": "net0", "virtual_machine__name": "web01"}],
            interfaces=[],
        )
        prefix = source.prefix(
            network="10.0.10.0", prefix_length=24, namespace__name="Global", status__name="Active", type="network"
        )
        for item in (vm, interface, ip_address, prefix):
            source.add(item)
        vm.add_child(interface)
        source.sync_to(self._nb_adapter())
        self.assertEqual(VirtualMachine.objects.get(name="web01").primary_ip.host, "10.0.10.50")

        source2 = self._source()
        self._seed_cluster(source2)
        vm2 = source2.virtual_machine(**_get_virtual_machine_dict({"name": "web01", "primary_ip4__host": "10.0.10.51"}))
        interface2 = source2.interface(**_get_vm_interface_dict({"name": "net0", "virtual_machine__name": "web01"}))
        ip_address2 = source2.ip_address(
            host="10.0.10.51",
            mask_length=24,
            status__name="Active",
            vm_interfaces=[{"name": "net0", "virtual_machine__name": "web01"}],
            interfaces=[],
        )
        prefix2 = source2.prefix(
            network="10.0.10.0", prefix_length=24, namespace__name="Global", status__name="Active", type="network"
        )
        for item in (vm2, interface2, ip_address2, prefix2):
            source2.add(item)
        vm2.add_child(interface2)
        source2.sync_to(self._nb_adapter())

        self.assertEqual(VirtualMachine.objects.get(name="web01").primary_ip.host, "10.0.10.51")

    def test_update_device_interface_link(self):
        """Adding a bridge relationship on re-sync links the two existing node Interfaces."""
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
        eth0 = source.device_interface(**_get_device_interface_dict({"name": "eth0", "device__name": "pve1"}))
        vmbr0 = source.device_interface(
            **_get_device_interface_dict({"name": "vmbr0", "device__name": "pve1", "type": "bridge"})
        )
        source.add(device)
        source.add(eth0)
        source.add(vmbr0)
        device.add_child(eth0)
        device.add_child(vmbr0)
        source.sync_to(self._nb_adapter())
        self.assertIsNone(Interface.objects.get(device__name="pve1", name="eth0").bridge)

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
        eth0_2 = source2.device_interface(
            **_get_device_interface_dict({"name": "eth0", "device__name": "pve1", "bridge__name": "vmbr0"})
        )
        vmbr0_2 = source2.device_interface(
            **_get_device_interface_dict({"name": "vmbr0", "device__name": "pve1", "type": "bridge"})
        )
        source2.add(device2)
        source2.add(eth0_2)
        source2.add(vmbr0_2)
        device2.add_child(eth0_2)
        device2.add_child(vmbr0_2)
        source2.sync_to(self._nb_adapter())

        updated_eth0 = Interface.objects.get(device__name="pve1", name="eth0")
        self.assertEqual(updated_eth0.bridge.name, "vmbr0")

    def test_tag_model_update(self):
        """Changing a Tag's description on re-sync updates the Nautobot Tag."""
        source = self._source()
        self._seed_cluster(source)
        tag = source.tag(name="custom-tag", description="v1")
        source.add(tag)
        source.sync_to(self._nb_adapter())
        self.assertEqual(Tag.objects.get(name="custom-tag").description, "v1")

        source2 = self._source()
        self._seed_cluster(source2)
        tag2 = source2.tag(name="custom-tag", description="v2")
        source2.add(tag2)
        source2.sync_to(self._nb_adapter())
        self.assertEqual(Tag.objects.get(name="custom-tag").description, "v2")
