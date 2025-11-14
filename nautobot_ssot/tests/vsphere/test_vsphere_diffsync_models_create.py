"""Test cases for vSphere DiffSync models and their create attribute."""

# pylint: disable=duplicate-code
from unittest.mock import MagicMock

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from nautobot.extras.models.statuses import Status
from nautobot.extras.models.tags import Tag
from nautobot.ipam.models import IPAddress, Prefix
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
        for tag_name in ["SSoT Synced from vSphere", "Owner__EEE"]:
            tag, _ = Tag.objects.get_or_create(name=tag_name)
            tag.content_types.add(ContentType.objects.get_for_model(VirtualMachine))
            tag.validated_save()

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
        owner_tag = self.vsphere_adapter.tag(name="Owner__EEE")
        sync_tag = self.vsphere_adapter.tag(name="SSoT Synced from vSphere")
        self.vsphere_adapter.add(owner_tag)
        self.vsphere_adapter.add(sync_tag)

        vm_test = self.vsphere_adapter.virtual_machine(
            **_get_virtual_machine_dict({"name": "TestVM", "tags": [{"name": "Owner__EEE"}]})
        )
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
        self.assertIn("SSoT Synced from vSphere", [tag.name for tag in nb_vm.tags.all()])
        self.assertIn("Owner__EEE", [tag.name for tag in nb_vm.tags.all()])

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

    def test_prefix_ipv6_creation(self):
        prefix_test = self.vsphere_adapter.prefix(
            network="2001:db8:85a3::",
            prefix_length=64,
            namespace__name="Global",
            status__name="Active",
            type="network",
        )
        self.vsphere_adapter.add(prefix_test)
        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()
        nb_adapter.load()
        self.vsphere_adapter.sync_to(nb_adapter)

        nb_prefix = Prefix.objects.get(network="2001:db8:85a3::", prefix_length=64)
        self.assertEqual(nb_prefix.network, "2001:db8:85a3::")
        self.assertEqual(nb_prefix.prefix_length, 64)
        self.assertEqual(str(nb_prefix.prefix), "2001:db8:85a3::/64")
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

    def test_vm_creation_and_vm_primary_ipv6(self):
        nb_clustergroup, _ = ClusterGroup.objects.get_or_create(name="TestClusterGroup")
        nb_clustertype, _ = ClusterType.objects.get_or_create(name="VMWare vSphere")
        Cluster.objects.create(
            name="TestCluster",
            cluster_group=nb_clustergroup,
            cluster_type=nb_clustertype,
        )

        vm_test = self.vsphere_adapter.virtual_machine(
            **_get_virtual_machine_dict(
                {"name": "TestVM", "primary_ip6__host": "2001:0db8:85a3:0000:0000:8a2e:0370:7334"}
            )
        )
        vm_interface_test = self.vsphere_adapter.interface(
            **_get_virtual_machine_interface_dict({"name": "Network Adapter 1", "virtual_machine__name": "TestVM"})
        )
        vm_interface_ip = self.vsphere_adapter.ip_address(
            host="2001:0db8:85a3:0000:0000:8a2e:0370:7334",
            mask_length=64,
            status__name="Active",
            vm_interfaces=[{"name": "Network Adapter 1", "virtual_machine__name": "TestVM"}],
        )
        prefix_test = self.vsphere_adapter.prefix(
            network="2001:0db8:85a3::",
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
        self.assertEqual(nb_vm.primary_ip.host, "2001:db8:85a3::8a2e:370:7334")

    def test_tag_creation(self):
        tag_test = self.vsphere_adapter.tag(name="Owner__EEE", description="", content_types=["VirtualMachine"])
        self.vsphere_adapter.add(tag_test)

        nb_adapter = NBAdapter(config=self.config, cluster_filters=None)
        nb_adapter.job = MagicMock()

        nb_adapter.load()
        self.vsphere_adapter.sync_to(nb_adapter)

        nb_tag = Tag.objects.get(name="Owner__EEE")
        self.assertEqual(nb_tag.name, "Owner__EEE")
