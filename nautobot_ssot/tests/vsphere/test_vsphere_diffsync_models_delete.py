# pylint: disable=duplicate-code
"""Test cases for vSphere DiffSync models and their delete attribute."""

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
from nautobot_ssot.tests.vsphere.utilities import _get_virtual_machine_dict, _get_virtual_machine_interface_dict

from .vsphere_fixtures import create_default_vsphere_config


class TestVSphereDiffSyncModelsDelete(TestCase):
    """Test cases for vSphere DiffSync models and their delete attribute."""

    def setUp(self):
        """Test class SetUp."""
        self.config = create_default_vsphere_config()
        self.vsphere_adapter = VsphereDiffSync(client=MagicMock(), config=self.config, cluster_filters=None)
        self.active_status, _ = Status.objects.get_or_create(name="Active")
        for model in [
            VirtualMachine,
            Cluster,
            ClusterType,
            ClusterGroup,
            VMInterface,
            IPAddress,
        ]:
            self.active_status.content_types.add(ContentType.objects.get_for_model(model))
            self.active_status.validated_save()
        self.ssot_tag, _ = Tag.objects.get_or_create(name="SSoT Synced from vSphere")

    def test_vm_delete(self):
        ClusterGroup.objects.get_or_create(name="TestClusterGroup")
        ClusterType.objects.get_or_create(name="VMWare vSphere")
        Cluster.objects.create(
            name="TestCluster",
            cluster_group=ClusterGroup.objects.get(name="TestClusterGroup"),
            cluster_type=ClusterType.objects.get(name="VMWare vSphere"),
        )
        nb_vm = VirtualMachine.objects.create(
            name="TestVM",
            status=self.active_status,
            vcpus=3,
            memory=4096,
            disk=50,
            cluster=Cluster.objects.get(name="TestCluster"),
        )
        nb_vm.tags.set([self.ssot_tag])
        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()
        self.vsphere_adapter.sync_to(nb_adapter)

        with self.assertRaises(VirtualMachine.DoesNotExist):
            VirtualMachine.objects.get(name="TestVM")

    def test_vminterface_delete(self):
        ClusterGroup.objects.get_or_create(name="TestClusterGroup")
        ClusterType.objects.get_or_create(name="VMWare vSphere")
        Cluster.objects.create(
            name="TestCluster",
            cluster_group=ClusterGroup.objects.get(name="TestClusterGroup"),
            cluster_type=ClusterType.objects.get(name="VMWare vSphere"),
        )
        nb_vm = VirtualMachine.objects.create(
            name="TestVM",
            status=self.active_status,
            vcpus=3,
            memory=4096,
            disk=50,
            cluster=Cluster.objects.get(name="TestCluster"),
        )
        nb_vm.tags.set([self.ssot_tag])
        VMInterface.objects.create(
            name="Network Adapter 1",
            enabled=True,
            virtual_machine=VirtualMachine.objects.get(name="TestVM"),
            mac_address="AA:AA:AA:AA:AA:AA",
            status=self.active_status,
        )

        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()
        self.vsphere_adapter.sync_to(nb_adapter)

        with self.assertRaises(VMInterface.DoesNotExist):
            VMInterface.objects.get(name="Network Adapter 1")

    def test_vm_primary_ip_delete(self):  # pylint: disable=too-many-locals
        ClusterGroup.objects.get_or_create(name="TestClusterGroup")
        ClusterType.objects.get_or_create(name="VMWare vSphere")
        Cluster.objects.create(
            name="TestCluster",
            cluster_group=ClusterGroup.objects.get(name="TestClusterGroup"),
            cluster_type=ClusterType.objects.get(name="VMWare vSphere"),
        )
        nb_vm = VirtualMachine.objects.create(
            name="TestVM",
            status=self.active_status,
            vcpus=3,
            memory=4096,
            disk=50,
            cluster=Cluster.objects.get(name="TestCluster"),
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
            **_get_virtual_machine_dict({"name": "TestVM", "primary_ip4__host": ""})
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
        self.assertEqual(nb_vm.primary_ip, None)

    def test_tag_delete(self):
        tag, _ = Tag.objects.get_or_create(name="Owner__EEE", description="")
        tag.content_types.set([ContentType.objects.get_for_model(VirtualMachine)])

        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()

        nb_adapter.load()
        self.vsphere_adapter.sync_to(nb_adapter)

        with self.assertRaises(Tag.DoesNotExist):
            Tag.objects.get(name="Owner__EEE")
