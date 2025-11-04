# pylint: disable=duplicate-code
"""Test cases for vSphere DiffSync models and their update attribute."""

from unittest.mock import MagicMock

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from nautobot.extras.models.statuses import Status
from nautobot.extras.models.tags import Tag
from nautobot.ipam.models import IPAddress, Namespace, Prefix
from nautobot.virtualization.models import (
    Cluster,
    ClusterGroup,
    ClusterType,
    VirtualMachine,
    VMInterface,
)

from nautobot_ssot.integrations.vsphere.diffsync.adapters.adapter_nautobot import (
    NBAdapter,
)
from nautobot_ssot.integrations.vsphere.diffsync.adapters.adapter_vsphere import (
    VsphereDiffSync,
)
from nautobot_ssot.integrations.vsphere.diffsync.models import ClusterGroupModel
from nautobot_ssot.tests.vsphere.utilities import _get_virtual_machine_dict, _get_virtual_machine_interface_dict

from .vsphere_fixtures import create_default_vsphere_config


class TestVSphereDiffSyncModelsUpdate(TestCase):
    """Test cases for vSphere DiffSync models."""

    def setUp(self):
        """Test class SetUp."""
        self.config = create_default_vsphere_config()
        self.vsphere_adapter = VsphereDiffSync(
            client=MagicMock(),
            config=self.config,
            cluster_filters=None,
        )
        self.active_status, _ = Status.objects.get_or_create(name="Active")
        self.ssot_tag, _ = Tag.objects.get_or_create(name="SSoT Synced from vSphere")
        self.operating_system_tag, _ = Tag.objects.get_or_create(name="Linux__Operating_System")

    def test_cluster_clustertype_update(self):
        ClusterGroup.objects.get_or_create(name="TestClusterGroup")
        ClusterType.objects.get_or_create(name="VMWare vSphere")
        ClusterType.objects.get_or_create(name="NewClusterType")

        clustergroup_test = self.vsphere_adapter.clustergroup(name="TestClusterGroup")
        cluster_test = self.vsphere_adapter.cluster(
            name="TestCluster",
            cluster_group__name="TestClusterGroup",
            cluster_type__name="NewClusterType",
        )
        self.vsphere_adapter.add(clustergroup_test)
        self.vsphere_adapter.add(cluster_test)
        diff_clustergroup = self.vsphere_adapter.get(ClusterGroupModel, {"name": "TestClusterGroup"})
        diff_clustergroup.add_child(cluster_test)

        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()
        self.vsphere_adapter.sync_to(nb_adapter)

        nb_cluster = Cluster.objects.get(name="TestCluster")
        self.assertEqual(nb_cluster.name, "TestCluster")
        self.assertEqual(nb_cluster.cluster_group.name, "TestClusterGroup")
        self.assertEqual(nb_cluster.cluster_type.name, "NewClusterType")

    def test_vm_update(self):
        nb_clustergroup, _ = ClusterGroup.objects.get_or_create(name="TestClusterGroup")
        nb_clustertype, _ = ClusterType.objects.get_or_create(name="VMWare vSphere")
        nb_cluster = Cluster.objects.create(
            name="TestCluster",
            cluster_group=nb_clustergroup,
            cluster_type=nb_clustertype,
        )
        nb_vm = VirtualMachine.objects.create(
            name="TestVM",
            status=self.active_status,
            vcpus=1,
            memory=1,
            disk=1,
            cluster=nb_cluster,
        )
        nb_vm.tags.set([self.ssot_tag])

        owner_tag = self.vsphere_adapter.tag(name="Linux__Operating_System")
        sync_tag = self.vsphere_adapter.tag(name="SSoT Synced from vSphere")
        self.vsphere_adapter.add(owner_tag)
        self.vsphere_adapter.add(sync_tag)

        vm_test = self.vsphere_adapter.virtual_machine(
            **_get_virtual_machine_dict(
                {
                    "name": "TestVM",
                    "vcpus": 100,
                    "memory": 100,
                    "disk": 100,
                    "tags": [{"name": "Linux__Operating_System"}],
                }
            )
        )

        self.vsphere_adapter.add(vm_test)

        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()
        self.vsphere_adapter.sync_to(nb_adapter)

        nb_vm = VirtualMachine.objects.get(name="TestVM")
        self.assertEqual(nb_vm.name, "TestVM")
        self.assertEqual(nb_vm.status.name, "Active")
        self.assertEqual(nb_vm.vcpus, 100)
        self.assertEqual(nb_vm.memory, 100)
        self.assertEqual(nb_vm.disk, 100)
        self.assertEqual(nb_vm.cluster.name, "TestCluster")
        # self.assertEqual(1, 2)

    def test_vminterface_update(self):
        nb_clustergroup, _ = ClusterGroup.objects.get_or_create(name="TestClusterGroup")
        nb_clustertype, _ = ClusterType.objects.get_or_create(name="VMWare vSphere")
        nb_cluster = Cluster.objects.create(
            name="TestCluster",
            cluster_group=nb_clustergroup,
            cluster_type=nb_clustertype,
        )
        nb_vm = VirtualMachine.objects.create(
            name="TestVM",
            status=self.active_status,
            vcpus=3,
            memory=4096,
            disk=50,
            cluster=nb_cluster,
        )
        nb_vm.tags.set([self.ssot_tag])
        VMInterface.objects.create(
            name="Network Adapter 1",
            enabled=True,
            virtual_machine=nb_vm,
            mac_address="AA:AA:AA:AA:AA:AA",
            status=self.active_status,
        )
        vm_test = self.vsphere_adapter.virtual_machine(**_get_virtual_machine_dict({"name": "TestVM"}))
        vm_interface_test = self.vsphere_adapter.interface(
            **_get_virtual_machine_interface_dict(
                {
                    "name": "Network Adapter 1",
                    "virtual_machine__name": "TestVM",
                    "mac_address": "AA:BB:CC:DD:EE:FF",
                    "enabled": False,
                }
            )
        )
        self.vsphere_adapter.add(vm_test)
        self.vsphere_adapter.add(vm_interface_test)
        vm_test.add_child(vm_interface_test)

        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()
        self.vsphere_adapter.sync_to(nb_adapter)

        nb_vminterface = VMInterface.objects.get(name="Network Adapter 1")
        self.assertEqual(nb_vminterface.name, "Network Adapter 1")
        self.assertEqual(nb_vminterface.enabled, False)
        self.assertEqual(nb_vminterface.virtual_machine.name, "TestVM")
        self.assertEqual(nb_vminterface.mac_address, "AA:BB:CC:DD:EE:FF")

    def test_ip_interface_update(self):
        nb_clustergroup, _ = ClusterGroup.objects.get_or_create(name="TestClusterGroup")
        nb_clustertype, _ = ClusterType.objects.get_or_create(name="VMWare vSphere")
        nb_cluster = Cluster.objects.create(
            name="TestCluster",
            cluster_group=nb_clustergroup,
            cluster_type=nb_clustertype,
        )
        nb_vm = VirtualMachine.objects.create(
            name="TestVM",
            status=self.active_status,
            vcpus=3,
            memory=4096,
            disk=50,
            cluster=nb_cluster,
        )
        nb_vm.tags.set([self.ssot_tag])
        nb_vm_interface_1 = VMInterface.objects.create(
            name="Network Adapter 1",
            enabled=True,
            virtual_machine=nb_vm,
            mac_address="AA:AA:AA:AA:AA:AA",
            status=self.active_status,
        )
        VMInterface.objects.create(
            name="Network Adapter 2",
            enabled=True,
            virtual_machine=nb_vm,
            mac_address="BB:BB:BB:BB:BB:BB",
            status=self.active_status,
        )
        Prefix.objects.create(
            network="192.168.1.0",
            prefix_length=24,
            namespace=Namespace.objects.get(name="Global"),
            status=self.active_status,
            type="network",
        )
        nb_ip = IPAddress.objects.create(host="192.168.1.1", mask_length=24, status=self.active_status)
        nb_ip.tags.set([self.ssot_tag])
        nb_ip.vm_interfaces.set([nb_vm_interface_1])

        vm_test = self.vsphere_adapter.virtual_machine(**_get_virtual_machine_dict({"name": "TestVM"}))
        vm_interface_test_1 = self.vsphere_adapter.interface(
            **_get_virtual_machine_interface_dict({"name": "Network Adapter 1", "virtual_machine__name": "TestVM"})
        )
        vm_interface_test_2 = self.vsphere_adapter.interface(
            **_get_virtual_machine_interface_dict(
                {
                    "name": "Network Adapter 2",
                    "virtual_machine__name": "TestVM",
                    "mac_address": "BB:BB:BB:BB:BB:BB",
                }
            )
        )
        vm_interface_ip = self.vsphere_adapter.ip_address(
            host="192.168.1.1",
            mask_length=24,
            status__name="Active",
            vm_interfaces=[{"name": "Network Adapter 2", "virtual_machine__name": "TestVM"}],
        )
        prefix_test = self.vsphere_adapter.prefix(
            network="192.168.1.0",
            prefix_length=24,
            namespace__name="Global",
            status__name="Active",
            type="network",
        )
        self.vsphere_adapter.add(vm_test)
        self.vsphere_adapter.add(vm_interface_test_1)
        self.vsphere_adapter.add(vm_interface_test_2)
        self.vsphere_adapter.add(vm_interface_ip)
        self.vsphere_adapter.add(prefix_test)
        vm_test.add_child(vm_interface_test_1)
        vm_test.add_child(vm_interface_test_2)

        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()
        self.vsphere_adapter.sync_to(nb_adapter)

        nb_ip = IPAddress.objects.get(host="192.168.1.1", mask_length=24)
        self.assertEqual(nb_ip.host, "192.168.1.1")
        self.assertEqual(nb_ip.mask_length, 24)
        self.assertIn(
            "Network Adapter 2",
            [interface.name for interface in nb_ip.vm_interfaces.all()],
        )

    def test_vm_primary_ip_update(self):  # pylint: disable=too-many-locals
        nb_clustergroup, _ = ClusterGroup.objects.get_or_create(name="TestClusterGroup")
        nb_clustertype, _ = ClusterType.objects.get_or_create(name="VMWare vSphere")
        nb_cluster = Cluster.objects.create(
            name="TestCluster",
            cluster_group=nb_clustergroup,
            cluster_type=nb_clustertype,
        )
        nb_vm = VirtualMachine.objects.create(
            name="TestVM",
            status=self.active_status,
            vcpus=3,
            memory=4096,
            disk=50,
            cluster=nb_cluster,
        )
        nb_vm.tags.set([self.ssot_tag])
        nb_vm_interface_1 = VMInterface.objects.create(
            name="Network Adapter 1",
            enabled=True,
            virtual_machine=nb_vm,
            mac_address="AA:BB:CC:DD:EE:FF",
            status=self.active_status,
        )
        nb_vm_interface_2 = VMInterface.objects.create(
            name="Network Adapter 2",
            enabled=True,
            virtual_machine=nb_vm,
            mac_address="BB:BB:BB:BB:BB:BB",
            status=self.active_status,
        )
        Prefix.objects.create(
            network="192.168.1.0",
            prefix_length=24,
            namespace=Namespace.objects.get(name="Global"),
            status=self.active_status,
            type="network",
        )
        Prefix.objects.create(
            network="10.10.10.0",
            prefix_length=24,
            namespace=Namespace.objects.get(name="Global"),
            status=self.active_status,
            type="network",
        )
        nb_ip_1 = IPAddress.objects.create(host="192.168.1.1", mask_length=24, status=self.active_status)
        nb_ip_1.tags.set([self.ssot_tag])
        nb_ip_2 = IPAddress.objects.create(host="10.10.10.1", mask_length=24, status=self.active_status)
        nb_ip_2.tags.set([self.ssot_tag])
        nb_ip_1.vm_interfaces.set([nb_vm_interface_1])
        nb_ip_2.vm_interfaces.set([nb_vm_interface_2])
        nb_vm.primary_ip4 = nb_ip_1
        nb_vm.validated_save()

        vm_test = self.vsphere_adapter.virtual_machine(
            **_get_virtual_machine_dict({"name": "TestVM", "primary_ip4__host": "10.10.10.1"})
        )
        vm_interface_test_1 = self.vsphere_adapter.interface(
            **_get_virtual_machine_interface_dict({"name": "Network Adapter 1", "virtual_machine__name": "TestVM"})
        )
        vm_interface_test_2 = self.vsphere_adapter.interface(
            **_get_virtual_machine_interface_dict(
                {
                    "name": "Network Adapter 2",
                    "virtual_machine__name": "TestVM",
                    "mac_address": "BB:BB:BB:BB:BB:BB",
                }
            )
        )
        vm_interface_ip_1 = self.vsphere_adapter.ip_address(
            host="192.168.1.1",
            mask_length=24,
            status__name="Active",
            vm_interfaces=[{"name": "Network Adapter 1", "virtual_machine__name": "TestVM"}],
        )
        vm_interface_ip_2 = self.vsphere_adapter.ip_address(
            host="10.10.10.1",
            mask_length=24,
            status__name="Active",
            vm_interfaces=[{"name": "Network Adapter 2", "virtual_machine__name": "TestVM"}],
        )
        prefix_test_1 = self.vsphere_adapter.prefix(
            network="192.168.1.0",
            prefix_length=24,
            namespace__name="Global",
            status__name="Active",
            type="network",
        )
        prefix_test_2 = self.vsphere_adapter.prefix(
            network="10.10.10.0",
            prefix_length=24,
            namespace__name="Global",
            status__name="Active",
            type="network",
        )
        self.vsphere_adapter.add(vm_test)
        self.vsphere_adapter.add(vm_interface_test_1)
        self.vsphere_adapter.add(vm_interface_test_2)
        self.vsphere_adapter.add(vm_interface_ip_1)
        self.vsphere_adapter.add(vm_interface_ip_2)
        self.vsphere_adapter.add(prefix_test_1)
        self.vsphere_adapter.add(prefix_test_2)
        vm_test.add_child(vm_interface_test_1)
        vm_test.add_child(vm_interface_test_2)

        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()

        self.vsphere_adapter.sync_to(nb_adapter)
        nb_adapter.sync_complete(source=None, diff=None)
        nb_vm = VirtualMachine.objects.get(name="TestVM")
        self.assertEqual(nb_vm.name, "TestVM")
        self.assertEqual(nb_vm.primary_ip.host, "10.10.10.1")

    def test_vm_primary_ip6_update(self):  # pylint: disable=too-many-locals
        nb_clustergroup, _ = ClusterGroup.objects.get_or_create(name="TestClusterGroup")
        nb_clustertype, _ = ClusterType.objects.get_or_create(name="VMWare vSphere")
        nb_cluster = Cluster.objects.create(
            name="TestCluster",
            cluster_group=nb_clustergroup,
            cluster_type=nb_clustertype,
        )
        nb_vm = VirtualMachine.objects.create(
            name="TestVM",
            status=self.active_status,
            vcpus=3,
            memory=4096,
            disk=50,
            cluster=nb_cluster,
        )
        nb_vm.tags.set([self.ssot_tag])
        nb_vm_interface_1 = VMInterface.objects.create(
            name="Network Adapter 1",
            enabled=True,
            virtual_machine=nb_vm,
            mac_address="AA:BB:CC:DD:EE:FF",
            status=self.active_status,
        )
        nb_vm_interface_2 = VMInterface.objects.create(
            name="Network Adapter 2",
            enabled=True,
            virtual_machine=nb_vm,
            mac_address="BB:BB:BB:BB:BB:BB",
            status=self.active_status,
        )
        Prefix.objects.create(
            network="fd12:3456:789a:1::",
            prefix_length=64,
            namespace=Namespace.objects.get(name="Global"),
            status=self.active_status,
            type="network",
        )
        Prefix.objects.create(
            network="2001:db8:abcd:42::",
            prefix_length=64,
            namespace=Namespace.objects.get(name="Global"),
            status=self.active_status,
            type="network",
        )
        nb_ip_1 = IPAddress.objects.create(host="fd12:3456:789a:1::1234", mask_length=64, status=self.active_status)
        nb_ip_1.tags.set([self.ssot_tag])
        nb_ip_2 = IPAddress.objects.create(host="2001:db8:abcd:42::abcd", mask_length=64, status=self.active_status)
        nb_ip_2.tags.set([self.ssot_tag])
        nb_ip_1.vm_interfaces.set([nb_vm_interface_1])
        nb_ip_2.vm_interfaces.set([nb_vm_interface_2])
        nb_vm.primary_ip6 = nb_ip_1
        nb_vm.validated_save()

        vm_test = self.vsphere_adapter.virtual_machine(
            **_get_virtual_machine_dict({"name": "TestVM", "primary_ip6__host": "2001:db8:abcd:42::abcd"})
        )
        vm_interface_test_1 = self.vsphere_adapter.interface(
            **_get_virtual_machine_interface_dict({"name": "Network Adapter 1", "virtual_machine__name": "TestVM"})
        )
        vm_interface_test_2 = self.vsphere_adapter.interface(
            **_get_virtual_machine_interface_dict(
                {
                    "name": "Network Adapter 2",
                    "virtual_machine__name": "TestVM",
                    "mac_address": "BB:BB:BB:BB:BB:BB",
                }
            )
        )
        vm_interface_ip_1 = self.vsphere_adapter.ip_address(
            host="fd12:3456:789a:1::1234",
            mask_length=64,
            status__name="Active",
            vm_interfaces=[{"name": "Network Adapter 1", "virtual_machine__name": "TestVM"}],
        )
        vm_interface_ip_2 = self.vsphere_adapter.ip_address(
            host="2001:db8:abcd:42::abcd",
            mask_length=64,
            status__name="Active",
            vm_interfaces=[{"name": "Network Adapter 2", "virtual_machine__name": "TestVM"}],
        )
        prefix_test_1 = self.vsphere_adapter.prefix(
            network="fd12:3456:789a:1::",
            prefix_length=64,
            namespace__name="Global",
            status__name="Active",
            type="network",
        )
        prefix_test_2 = self.vsphere_adapter.prefix(
            network="2001:db8:abcd:42::",
            prefix_length=64,
            namespace__name="Global",
            status__name="Active",
            type="network",
        )
        self.vsphere_adapter.add(vm_test)
        self.vsphere_adapter.add(vm_interface_test_1)
        self.vsphere_adapter.add(vm_interface_test_2)
        self.vsphere_adapter.add(vm_interface_ip_1)
        self.vsphere_adapter.add(vm_interface_ip_2)
        self.vsphere_adapter.add(prefix_test_1)
        self.vsphere_adapter.add(prefix_test_2)
        vm_test.add_child(vm_interface_test_1)
        vm_test.add_child(vm_interface_test_2)

        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()

        self.vsphere_adapter.sync_to(nb_adapter)
        nb_adapter.sync_complete(source=None, diff=None)
        nb_vm = VirtualMachine.objects.get(name="TestVM")
        self.assertEqual(nb_vm.name, "TestVM")
        self.assertEqual(nb_vm.primary_ip.host, "2001:db8:abcd:42::abcd")

    def test_tag_update(self):
        tag, _ = Tag.objects.get_or_create(name="Owner__EEE", description="")
        tag.content_types.set([ContentType.objects.get_for_model(VirtualMachine)])

        tag_test_updated = self.vsphere_adapter.tag(
            name="Owner__EEE", description="Updated description", content_types=["VirtualMachine"]
        )
        self.vsphere_adapter.add(tag_test_updated)

        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()

        nb_adapter.load()
        self.vsphere_adapter.sync_to(nb_adapter)

        nb_tag = Tag.objects.get(name="Owner__EEE")
        self.assertEqual(nb_tag.name, "Owner__EEE")
        self.assertEqual(nb_tag.description, "Updated description")
