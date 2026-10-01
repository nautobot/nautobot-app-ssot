"""Create-path tests for the Proxmox VE DiffSync models (DB-backed)."""

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device, Interface
from nautobot.extras.models import RelationshipAssociation, Tag
from nautobot.ipam.models import IPAddress, Prefix
from nautobot.virtualization.models import Cluster, ClusterGroup, VirtualMachine

from nautobot_ssot.integrations.proxmox.constants import HOST_RELATIONSHIP_KEY, SSOT_TAG_NAME

from .proxmox_fixtures import (
    ProxmoxSyncTestMixin,
    _get_device_interface_dict,
    _get_node_device_dict,
    _get_virtual_machine_dict,
    _get_vm_interface_dict,
)


class TestProxmoxDiffSyncModelsCreate(ProxmoxSyncTestMixin, TestCase):
    """Syncing new source models creates the matching Nautobot objects."""

    def setUp(self):
        """Create default objects and an empty source adapter."""
        super().setUp()
        self.source = self._source()

    def test_cluster_creation(self):
        """A Cluster and its ClusterGroup are created."""
        self._seed_cluster(self.source)
        self.source.sync_to(self._nb_adapter())

        cluster = Cluster.objects.get(name="TestCluster")
        self.assertEqual(cluster.cluster_type.name, "Proxmox VE")
        self.assertEqual(cluster.cluster_group.name, "TestClusterGroup")
        self.assertTrue(ClusterGroup.objects.filter(name="TestClusterGroup").exists())

    def test_device_creation_with_cluster_and_hardware(self):
        """A node Device is created with its cluster, hardware custom fields and SSoT tag."""
        self._seed_cluster(self.source)
        device = self.source.device(
            **_get_node_device_dict(
                {"name": "pve1", "pve_version": "pve-manager/8.1.4/example", "cpu_count": 16, "memory_gb": 62}
            )
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
        # Date only: Nautobot has no datetime custom field type.
        last_synced = str(nb_device.cf["last_synced_from_proxmox_on"])
        self.assertRegex(last_synced, r"^\d{4}-\d{2}-\d{2}$")

    def test_device_interface_topology(self):
        """A node Interface is linked to its bridge after sync_complete()."""
        self._seed_cluster(self.source)
        device = self.source.device(**_get_node_device_dict({"name": "pve1"}))
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
        """A VM is created with its tags and a host relationship to its node Device."""
        self._seed_cluster(self.source)
        device = self.source.device(**_get_node_device_dict({"name": "pve1"}))
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
        """A VM interface IP, its Prefix and the VM's primary IP are created."""
        self._seed_cluster(self.source)
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
        """A node interface IP is created and set as the Device's primary IP."""
        self._seed_cluster(self.source)
        device = self.source.device(**_get_node_device_dict({"name": "pve1", "primary_ip4__host": "10.0.0.1"}))
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
        """A source Tag is created with its description and the VirtualMachine content type."""
        self._seed_cluster(self.source)
        custom_tag = self.source.tag(name="custom-tag", description="A custom tag")
        self.source.add(custom_tag)
        self.source.sync_to(self._nb_adapter())

        nb_tag = Tag.objects.get(name="custom-tag")
        self.assertEqual(nb_tag.description, "A custom tag")
        self.assertIn(ContentType.objects.get_for_model(VirtualMachine), nb_tag.content_types.all())
