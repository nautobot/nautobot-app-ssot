# pylint: disable=R0801
"""Create-path tests for the Proxmox VE DiffSync models (DB-backed)."""

from unittest.mock import MagicMock

from django.apps import apps as django_apps
from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device, Interface
from nautobot.extras.models import RelationshipAssociation, Tag
from nautobot.ipam.models import IPAddress, Prefix
from nautobot.virtualization.models import Cluster, ClusterGroup, VirtualMachine

from nautobot_ssot.integrations.proxmox.constants import HOST_RELATIONSHIP_KEY, SSOT_TAG_DESCRIPTION, SSOT_TAG_NAME
from nautobot_ssot.integrations.proxmox.diffsync.adapters.adapter_nautobot import NBAdapter
from nautobot_ssot.integrations.proxmox.diffsync.adapters.adapter_proxmox import ProxmoxDiffSync
from nautobot_ssot.integrations.proxmox.signals import nautobot_database_ready_callback

from .proxmox_fixtures import (
    _get_device_interface_dict,
    _get_virtual_machine_dict,
    _get_vm_interface_dict,
    create_default_proxmox_config,
)


class TestProxmoxDiffSyncModelsCreate(TestCase):
    """Create-path tests: build source models, sync to Nautobot, assert ORM state."""

    def setUp(self):
        """Build the signal-managed scaffolding and a source adapter seeded with a cluster."""
        nautobot_database_ready_callback(sender=None, apps=django_apps)
        self.config = create_default_proxmox_config()
        self.source = ProxmoxDiffSync(
            job=MagicMock(), sync=MagicMock(), client=MagicMock(), config=self.config, cluster_filters=None
        )

    def _nb_adapter(self):
        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()
        return nb_adapter

    def _seed_cluster(self):
        """Add the SSoT tag + a ClusterGroup + Cluster to the source adapter (mirrors adapter.load())."""
        self.source.add(self.source.tag(name=SSOT_TAG_NAME, description=SSOT_TAG_DESCRIPTION))
        clustergroup = self.source.clustergroup(name="TestClusterGroup")
        cluster = self.source.cluster(
            name="TestCluster", cluster_type__name="Proxmox VE", cluster_group__name="TestClusterGroup"
        )
        self.source.add(clustergroup)
        self.source.add(cluster)
        clustergroup.add_child(cluster)
        return cluster

    def test_cluster_creation(self):
        self._seed_cluster()
        self.source.sync_to(self._nb_adapter())

        cluster = Cluster.objects.get(name="TestCluster")
        self.assertEqual(cluster.cluster_type.name, "Proxmox VE")
        self.assertEqual(cluster.cluster_group.name, "TestClusterGroup")
        self.assertTrue(ClusterGroup.objects.filter(name="TestClusterGroup").exists())

    def test_device_creation_with_cluster_and_hardware(self):
        self._seed_cluster()
        device = self.source.device(
            name="pve1",
            device_type__model="Proxmox Node",
            role__name="Proxmox Node",
            location__name="Proxmox VE Default Location",
            status__name="Active",
            clusters=[{"name": "TestCluster"}],
            pve_version="pve-manager/8.1.4/example",
            cpu_count=16,
            memory_gb=62,
        )
        self.source.add(device)
        self.source.sync_to(self._nb_adapter())

        nb_device = Device.objects.get(name="pve1")
        self.assertEqual(nb_device.role.name, "Proxmox Node")
        self.assertEqual(nb_device.location.name, "Proxmox VE Default Location")
        self.assertIn("TestCluster", [cluster.name for cluster in nb_device.clusters.all()])
        self.assertEqual(nb_device.cf["proxmox_pve_version"], "pve-manager/8.1.4/example")
        self.assertEqual(nb_device.cf["proxmox_cpu_count"], 16)
        self.assertEqual(nb_device.cf["proxmox_memory_gb"], 62)
        self.assertIn(SSOT_TAG_NAME, [tag.name for tag in nb_device.tags.all()])
        # The last-synced custom field records date AND time (minute precision), not just a date.
        last_synced = str(nb_device.cf["last_synced_from_proxmox_on"])
        self.assertIn("T", last_synced)
        self.assertIn(":", last_synced)

    def test_device_interface_topology(self):
        self._seed_cluster()
        device = self.source.device(
            name="pve1",
            device_type__model="Proxmox Node",
            role__name="Proxmox Node",
            location__name="Proxmox VE Default Location",
            status__name="Active",
            clusters=[{"name": "TestCluster"}],
        )
        bridge = self.source.device_interface(
            **_get_device_interface_dict({"name": "vmbr0", "device__name": "pve1", "type": "bridge"})
        )
        member = self.source.device_interface(
            **_get_device_interface_dict({"name": "eth0", "device__name": "pve1", "bridge__name": "vmbr0"})
        )
        self.source.add(device)
        self.source.add(bridge)
        self.source.add(member)
        device.add_child(bridge)
        device.add_child(member)

        nb_adapter = self._nb_adapter()
        self.source.sync_to(nb_adapter)
        nb_adapter.sync_complete(source=None, diff=None)

        eth0 = Interface.objects.get(device__name="pve1", name="eth0")
        self.assertIsNotNone(eth0.bridge)
        self.assertEqual(eth0.bridge.name, "vmbr0")

    def test_vm_creation_with_host_relationship_and_tags(self):
        self._seed_cluster()
        device = self.source.device(
            name="pve1",
            device_type__model="Proxmox Node",
            role__name="Proxmox Node",
            location__name="Proxmox VE Default Location",
            status__name="Active",
            clusters=[{"name": "TestCluster"}],
        )
        owner_tag = self.source.tag(name="prod")
        vm = self.source.virtual_machine(
            **_get_virtual_machine_dict(
                {"name": "web01", "host_device": {"name": "pve1"}, "tags": [{"name": "prod"}, {"name": SSOT_TAG_NAME}]}
            )
        )
        for item in (device, owner_tag, vm):
            self.source.add(item)
        self.source.sync_to(self._nb_adapter())

        nb_vm = VirtualMachine.objects.get(name="web01")
        self.assertEqual(nb_vm.cluster.name, "TestCluster")
        self.assertEqual(nb_vm.vcpus, 4)
        self.assertIn(SSOT_TAG_NAME, [tag.name for tag in nb_vm.tags.all()])
        self.assertIn("prod", [tag.name for tag in nb_vm.tags.all()])
        nb_device = Device.objects.get(name="pve1")
        self.assertTrue(
            RelationshipAssociation.objects.filter(
                relationship__key=HOST_RELATIONSHIP_KEY, source_id=nb_device.id, destination_id=nb_vm.id
            ).exists()
        )

    def test_vm_creation_with_interface_ip_and_primary(self):
        self._seed_cluster()
        vm = self.source.virtual_machine(
            **_get_virtual_machine_dict({"name": "web01", "primary_ip4__host": "10.0.10.50"})
        )
        interface = self.source.interface(**_get_vm_interface_dict({"name": "net0", "virtual_machine__name": "web01"}))
        ip_address = self.source.ip_address(
            host="10.0.10.50",
            mask_length=24,
            status__name="Active",
            vm_interfaces=[{"name": "net0", "virtual_machine__name": "web01"}],
            interfaces=[],
        )
        prefix = self.source.prefix(
            network="10.0.10.0", prefix_length=24, namespace__name="Global", status__name="Active", type="network"
        )
        for item in (vm, interface, ip_address, prefix):
            self.source.add(item)
        vm.add_child(interface)

        nb_adapter = self._nb_adapter()
        self.source.sync_to(nb_adapter)
        nb_adapter.sync_complete(source=None, diff=None)

        nb_ip = IPAddress.objects.get(host="10.0.10.50", mask_length=24)
        self.assertIn("net0", [iface.name for iface in nb_ip.vm_interfaces.all()])
        self.assertTrue(Prefix.objects.filter(network="10.0.10.0", prefix_length=24).exists())
        nb_vm = VirtualMachine.objects.get(name="web01")
        self.assertEqual(nb_vm.primary_ip.host, "10.0.10.50")

    def test_node_interface_ip_and_device_primary_ip(self):
        self._seed_cluster()
        device = self.source.device(
            name="pve1",
            device_type__model="Proxmox Node",
            role__name="Proxmox Node",
            location__name="Proxmox VE Default Location",
            status__name="Active",
            clusters=[{"name": "TestCluster"}],
            primary_ip4__host="10.0.0.1",
        )
        bridge = self.source.device_interface(
            **_get_device_interface_dict({"name": "vmbr0", "device__name": "pve1", "type": "bridge"})
        )
        ip_address = self.source.ip_address(
            host="10.0.0.1",
            mask_length=24,
            status__name="Active",
            vm_interfaces=[],
            interfaces=[{"name": "vmbr0", "device__name": "pve1"}],
        )
        prefix = self.source.prefix(
            network="10.0.0.0", prefix_length=24, namespace__name="Global", status__name="Active", type="network"
        )
        for item in (device, bridge, ip_address, prefix):
            self.source.add(item)
        device.add_child(bridge)

        nb_adapter = self._nb_adapter()
        self.source.sync_to(nb_adapter)
        nb_adapter.sync_complete(source=None, diff=None)

        nb_ip = IPAddress.objects.get(host="10.0.0.1", mask_length=24)
        self.assertIn("vmbr0", [iface.name for iface in nb_ip.interfaces.all()])
        nb_device = Device.objects.get(name="pve1")
        self.assertEqual(nb_device.primary_ip.host, "10.0.0.1")

    def test_tag_creation(self):
        """A Tag hand-rolled outside the contrib flow is created with a color and content types."""
        self._seed_cluster()
        custom_tag = self.source.tag(name="custom-tag", description="A custom tag")
        self.source.add(custom_tag)
        self.source.sync_to(self._nb_adapter())

        nb_tag = Tag.objects.get(name="custom-tag")
        self.assertEqual(nb_tag.description, "A custom tag")
        self.assertIn(ContentType.objects.get_for_model(VirtualMachine), nb_tag.content_types.all())
