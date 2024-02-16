"""Nautobot Adapter Tests"""

from unittest.mock import MagicMock

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
    Adapter,
)
from nautobot_ssot.integrations.vsphere.diffsync.models.vsphere import (
    ClusterGroupModel,
    ClusterModel,
    VirtualMachineModel,
    VMInterfaceModel,
)

from .vsphere_fixtures import create_default_vsphere_config


class TestNautobotAdapter(TestCase):  # pylint: disable=too-many-instance-attributes
    """Test cases for vSphere Nautobot adapter."""

    def setUp(self):
        test_cluster_type, _ = ClusterType.objects.get_or_create(name="Test")
        self.test_cluster_group, _ = ClusterGroup.objects.get_or_create(name="Test Group")
        self.test_cluster, _ = Cluster.objects.get_or_create(
            name="Test Cluster",
            cluster_type=test_cluster_type,
            cluster_group=self.test_cluster_group,
        )
        self.status, _ = Status.objects.get_or_create(name="Active")
        self.tags = [Tag.objects.create(name=tag_name) for tag_name in ["Tag Test 1", "Tag Test 2", "Tag Test 3"]]
        self.test_virtualmachine, _ = VirtualMachine.objects.get_or_create(
            name="Test VM",
            cluster=self.test_cluster,
            status=self.status,
            vcpus=2,
            memory=4094,
            disk=50,
        )
        self.test_virtualmachine.tags.set(self.tags)
        self.vm_interface_1, _ = VMInterface.objects.get_or_create(
            name="Test Interface",
            enabled=True,
            virtual_machine=self.test_virtualmachine,
            mac_address="AA:BB:CC:DD:EE:FF",
            status=self.status,
        )

        self.prefix, _ = Prefix.objects.get_or_create(
            network="192.168.1.0",
            prefix_length=24,
            namespace=Namespace.objects.get(name="Global"),
            status=self.status,
            type="network",
        )
        self.vm_ip, _ = IPAddress.objects.get_or_create(host="192.168.1.1", mask_length=24, status=self.status)
        self.vm_ip.vm_interfaces.set([self.vm_interface_1])

    def test_load(self):
        self.test_virtualmachine.primary_ip4 = self.vm_ip
        self.test_virtualmachine.validated_save()
        adapter = Adapter(job=MagicMock(), config=create_default_vsphere_config())
        adapter.load()
        # ClusterGroup Asserts
        diffsync_clustergroup = adapter.get(ClusterGroupModel, {"name": "Test Group"})
        self.assertEqual(diffsync_clustergroup.name, "Test Group")
        # Cluster Asserts
        diffsync_cluster = adapter.get(ClusterModel, {"name": "Test Cluster"})
        self.assertEqual(diffsync_cluster.name, "Test Cluster")
        self.assertEqual(diffsync_cluster.cluster_type__name, "Test")
        self.assertEqual(diffsync_cluster.cluster_group__name, "Test Group")
        # VirtualMachine Asserts
        diffsync_virtualmachine = adapter.get(VirtualMachineModel, {"name": "Test VM"})
        self.assertEqual(diffsync_virtualmachine.name, "Test VM")
        self.assertEqual(diffsync_virtualmachine.cluster__name, "Test Cluster")
        self.assertEqual(diffsync_virtualmachine.status__name, "Active")
        self.assertEqual(diffsync_virtualmachine.vcpus, 2)
        self.assertEqual(diffsync_virtualmachine.memory, 4094)
        self.assertEqual(diffsync_virtualmachine.disk, 50)
        self.assertEqual(diffsync_virtualmachine.primary_ip4__host, "192.168.1.1")

        # VMInterface Asserts
        diffsync_vminterface = adapter.get(
            VMInterfaceModel,
            {"name": "Test Interface", "virtual_machine__name": "Test VM"},
        )
        self.assertEqual(diffsync_vminterface.name, "Test Interface")
        self.assertEqual(diffsync_vminterface.virtual_machine__name, "Test VM")
        self.assertEqual(diffsync_vminterface.enabled, True)
        self.assertEqual(diffsync_vminterface.mac_address, "AA:BB:CC:DD:EE:FF")
