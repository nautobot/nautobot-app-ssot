"""Unit tests for vSphere SSoT DiffSync Models."""

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

from .vsphere_fixtures import create_default_vsphere_config


def _get_virtual_machine_dict(attrs):
    """Build dict used for creating diffsync Virtual Machine."""
    virtual_machine_dict = {
        "status__name": "Active",
        "vcpus": 3,
        "memory": 4096,
        "disk": 50,
        "cluster__name": "TestCluster",
        "primary_ip4__host": None,
        "primary_ip6__host": None,
    }
    virtual_machine_dict.update(attrs)
    return virtual_machine_dict


def _get_virtual_machine_interface_dict(attrs):
    """Build dict used for creating diffsync VM Interface."""
    vm_interface_dict = {
        "enabled": True,
        "status__name": "Active",
        "mac_address": "AA:BB:CC:DD:EE:FF",
    }
    vm_interface_dict.update(attrs)
    return vm_interface_dict


class TestVSphereDiffSyncModelsCreate(TestCase):
    """Test cases for vSphere DiffSync models."""

    def setUp(self):
        """Test class SetUp."""
        self.config = create_default_vsphere_config()
        self.vsphere_adapter = VsphereDiffSync(
            job=MagicMock(),
            sync=MagicMock(),
            client=MagicMock(),
            config=self.config,
            cluster_filters=None,
        )
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

    def test_clustergroup_creation(self):
        clustergroup_test = self.vsphere_adapter.clustergroup(name="TestClusterGroup")

        self.vsphere_adapter.add(clustergroup_test)

        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()

        nb_adapter.load()
        self.vsphere_adapter.sync_to(nb_adapter)

        nb_clustergroup = ClusterGroup.objects.get(name="TestClusterGroup")
        self.assertEqual(nb_clustergroup.name, "TestClusterGroup")

    def test_cluster_creation(self):
        ClusterType.objects.get_or_create(name="VMWare vSphere")
        clustergroup_test = self.vsphere_adapter.clustergroup(name="TestClusterGroup")
        cluster_test = self.vsphere_adapter.cluster(
            name="TestCluster",
            cluster_group__name="TestClusterGroup",
            cluster_type__name="VMWare vSphere",
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
        self.assertEqual(nb_cluster.cluster_type.name, "VMWare vSphere")

    def test_vm_creation(self):
        nb_clustergroup, _ = ClusterGroup.objects.get_or_create(name="TestClusterGroup")
        nb_clustertype, _ = ClusterType.objects.get_or_create(name="VMWare vSphere")
        Cluster.objects.create(
            name="TestCluster",
            cluster_group=nb_clustergroup,
            cluster_type=nb_clustertype,
        )

        vm_test = self.vsphere_adapter.virtual_machine(**_get_virtual_machine_dict({"name": "TestVM"}))
        self.vsphere_adapter.add(vm_test)

        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()
        self.vsphere_adapter.sync_to(nb_adapter)

        nb_vm = VirtualMachine.objects.get(name="TestVM")
        self.assertEqual(nb_vm.name, "TestVM")
        self.assertEqual(nb_vm.status.name, "Active")
        self.assertEqual(nb_vm.vcpus, 3)
        self.assertEqual(nb_vm.memory, 4096)
        self.assertEqual(nb_vm.disk, 50)
        self.assertEqual(nb_vm.cluster.name, "TestCluster")

    def test_vminterface_creation(self):
        nb_clustergroup, _ = ClusterGroup.objects.get_or_create(name="TestClusterGroup")
        nb_clustertype, _ = ClusterType.objects.get_or_create(name="VMWare vSphere")
        Cluster.objects.create(
            name="TestCluster",
            cluster_group=nb_clustergroup,
            cluster_type=nb_clustertype,
        )

        vm_test = self.vsphere_adapter.virtual_machine(**_get_virtual_machine_dict({"name": "TestVM"}))
        vm_interface_test = self.vsphere_adapter.interface(
            **_get_virtual_machine_interface_dict({"name": "Network Adapter 1", "virtual_machine__name": "TestVM"})
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
        self.assertEqual(nb_vminterface.enabled, True)
        self.assertEqual(nb_vminterface.virtual_machine.name, "TestVM")

    def test_ipaddress_creation_no_existing_prefix(self):
        nb_clustergroup, _ = ClusterGroup.objects.get_or_create(name="TestClusterGroup")
        nb_clustertype, _ = ClusterType.objects.get_or_create(name="VMWare vSphere")
        Cluster.objects.create(
            name="TestCluster",
            cluster_group=nb_clustergroup,
            cluster_type=nb_clustertype,
        )

        vm_test = self.vsphere_adapter.virtual_machine(**_get_virtual_machine_dict({"name": "TestVM"}))
        vm_interface_test = self.vsphere_adapter.interface(
            **_get_virtual_machine_interface_dict({"name": "Network Adapter 1", "virtual_machine__name": "TestVM"})
        )
        vm_interface_ip = self.vsphere_adapter.ip_address(
            host="192.168.1.1",
            mask_length=24,
            status__name="Active",
            vm_interfaces=[{"name": "Network Adapter 1", "virtual_machine__name": "TestVM"}],
        )
        prefix_test = self.vsphere_adapter.prefix(
            network="192.168.1.0",
            prefix_length=24,
            namespace__name="Global",
            status__name="Active",
            type="network",
        )
        self.vsphere_adapter.add(vm_test)
        self.vsphere_adapter.add(vm_interface_test)
        self.vsphere_adapter.add(vm_interface_ip)
        self.vsphere_adapter.add(prefix_test)
        vm_test.add_child(vm_interface_test)
        vm_interface_test.add_child(vm_interface_ip)

        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()
        self.vsphere_adapter.sync_to(nb_adapter)

        nb_ip = IPAddress.objects.get(host="192.168.1.1", mask_length=24)
        self.assertEqual(nb_ip.host, "192.168.1.1")
        self.assertEqual(nb_ip.mask_length, 24)
        self.assertIn(
            "Network Adapter 1",
            [interface.name for interface in nb_ip.vm_interfaces.all()],
        )

    def test_prefix_creation(self):
        prefix_test = self.vsphere_adapter.prefix(
            network="192.168.10.0",
            prefix_length=24,
            namespace__name="Global",
            status__name="Active",
            type="network",
        )
        self.vsphere_adapter.add(prefix_test)

        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()
        self.vsphere_adapter.sync_to(nb_adapter)

        nb_prefix = Prefix.objects.get(network="192.168.10.0", prefix_length=24)
        self.assertEqual(nb_prefix.network, "192.168.10.0")
        self.assertEqual(nb_prefix.prefix_length, 24)
        self.assertEqual(str(nb_prefix.prefix), "192.168.10.0/24")
        self.assertEqual(nb_prefix.namespace.name, "Global")
        self.assertEqual(nb_prefix.type, "network")

    def test_vm_creation_and_vm_primary_ip(self):
        nb_clustergroup, _ = ClusterGroup.objects.get_or_create(name="TestClusterGroup")
        nb_clustertype, _ = ClusterType.objects.get_or_create(name="VMWare vSphere")
        Cluster.objects.create(
            name="TestCluster",
            cluster_group=nb_clustergroup,
            cluster_type=nb_clustertype,
        )

        vm_test = self.vsphere_adapter.virtual_machine(
            **_get_virtual_machine_dict({"name": "TestVM", "primary_ip4__host": "192.168.1.1"})
        )
        vm_interface_test = self.vsphere_adapter.interface(
            **_get_virtual_machine_interface_dict({"name": "Network Adapter 1", "virtual_machine__name": "TestVM"})
        )
        vm_interface_ip = self.vsphere_adapter.ip_address(
            host="192.168.1.1",
            mask_length=24,
            status__name="Active",
            vm_interfaces=[{"name": "Network Adapter 1", "virtual_machine__name": "TestVM"}],
        )
        prefix_test = self.vsphere_adapter.prefix(
            network="192.168.1.0",
            prefix_length=24,
            namespace__name="Global",
            status__name="Active",
            type="network",
        )

        self.vsphere_adapter.add(vm_test)
        self.vsphere_adapter.add(vm_interface_test)
        self.vsphere_adapter.add(vm_interface_ip)
        self.vsphere_adapter.add(prefix_test)
        vm_test.add_child(vm_interface_test)
        vm_interface_test.add_child(vm_interface_ip)

        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()
        self.vsphere_adapter.sync_to(nb_adapter)

        nb_adapter.sync_complete(source=None, diff=None)
        nb_vm = VirtualMachine.objects.get(name="TestVM")
        self.assertEqual(nb_vm.name, "TestVM")
        self.assertEqual(nb_vm.status.name, "Active")
        self.assertEqual(nb_vm.vcpus, 3)
        self.assertEqual(nb_vm.memory, 4096)
        self.assertEqual(nb_vm.disk, 50)
        self.assertEqual(nb_vm.cluster.name, "TestCluster")
        self.assertEqual(nb_vm.primary_ip.host, "192.168.1.1")


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
        vm_test = self.vsphere_adapter.virtual_machine(
            **_get_virtual_machine_dict({"name": "TestVM", "vcpus": 100, "memory": 100, "disk": 100})
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
        vm_interface_test_1.add_child(vm_interface_ip)

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
        nb_ip_2 = IPAddress.objects.create(host="10.10.10.1", mask_length=24, status=self.active_status)
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
        vm_interface_test_1.add_child(vm_interface_ip_1)
        vm_interface_test_2.add_child(vm_interface_ip_2)

        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()

        self.vsphere_adapter.sync_to(nb_adapter)
        nb_adapter.sync_complete(source=None, diff=None)
        nb_vm = VirtualMachine.objects.get(name="TestVM")
        self.assertEqual(nb_vm.name, "TestVM")
        self.assertEqual(nb_vm.primary_ip.host, "10.10.10.1")


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
        nb_ip_2 = IPAddress.objects.create(host="10.10.10.1", mask_length=24, status=self.active_status)
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
        vm_interface_test_1.add_child(vm_interface_ip_1)
        vm_interface_test_2.add_child(vm_interface_ip_2)

        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()

        self.vsphere_adapter.sync_to(nb_adapter)
        nb_adapter.sync_complete(source=None, diff=None)
        nb_vm = VirtualMachine.objects.get(name="TestVM")
        self.assertEqual(nb_vm.name, "TestVM")
        self.assertEqual(nb_vm.primary_ip, None)
