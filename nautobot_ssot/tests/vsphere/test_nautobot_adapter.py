"""Nautobot Adapter Tests"""

# pylint: disable=protected-access
from unittest.mock import MagicMock

from nautobot.apps.testing import TestCase
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
from nautobot_ssot.integrations.vsphere.diffsync.models.vsphere import (
    ClusterGroupModel,
    ClusterModel,
    VirtualMachineModel,
    VMInterfaceModel,
)

from .vsphere_fixtures import create_default_vsphere_config


class TestNautobotAdapter(TestCase):  # pylint: disable=too-many-instance-attributes
    """Test cases for vSphere Nautobot adapter."""

    @classmethod
    def setUpTestData(cls):
        test_cluster_type, _ = ClusterType.objects.get_or_create(name="Test")
        cls.test_cluster_group, _ = ClusterGroup.objects.get_or_create(name="Test Group")
        cls.test_cluster, _ = Cluster.objects.update_or_create(
            name="Test Cluster",
            defaults={
                "cluster_type": test_cluster_type,
                "cluster_group": cls.test_cluster_group,
            },
        )
        cls.status, _ = Status.objects.get_or_create(name="Active")
        cls.ssot_tag, _ = Tag.objects.get_or_create(name="SSoT Synced from vSphere")
        cls.test_virtualmachine, _ = VirtualMachine.objects.get_or_create(
            name="Test VM",
            cluster=cls.test_cluster,
            status=cls.status,
            vcpus=2,
            memory=4094,
            disk=50,
        )
        cls.test_virtualmachine.tags.set([cls.ssot_tag])
        cls.vm_interface_1, _ = VMInterface.objects.get_or_create(
            name="Test Interface",
            enabled=True,
            virtual_machine=cls.test_virtualmachine,
            mac_address="AA:BB:CC:DD:EE:FF",
            status=cls.status,
        )

        cls.prefix, _ = Prefix.objects.get_or_create(
            network="192.168.1.0",
            prefix_length=24,
            namespace=Namespace.objects.get(name="Global"),
            status=cls.status,
            type="network",
        )
        cls.vm_ip, _ = IPAddress.objects.get_or_create(host="192.168.1.1", mask_length=24, status=cls.status)
        cls.vm_ip.vm_interfaces.set([cls.vm_interface_1])

    def test_load(self):
        self.test_virtualmachine.primary_ip4 = self.vm_ip
        self.test_virtualmachine.validated_save()
        adapter = NBAdapter(
            job=MagicMock(),
            config=create_default_vsphere_config(),
            cluster_filters=None,
        )
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
        diffsync_virtualmachine = adapter.get(VirtualMachineModel, {"name": "Test VM", "cluster__name": "Test Cluster"})
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

    def _make_adapter(self):
        """Return an NBAdapter with a mocked job."""
        adapter = NBAdapter(
            job=MagicMock(),
            config=create_default_vsphere_config(),
            cluster_filters=None,
        )
        return adapter

    def test_sync_complete_sets_primary_ip4(self):
        """sync_complete assigns primary_ip4 when present in _primary_ips."""
        adapter = self._make_adapter()
        adapter._primary_ips = [
            {
                "device": {"name": "Test VM"},
                "primary_ip4": "192.168.1.1",
                "primary_ip6": None,
            }
        ]

        adapter.sync_complete(source=MagicMock(), diff=MagicMock())

        self.test_virtualmachine.refresh_from_db()
        self.assertEqual(self.test_virtualmachine.primary_ip4, self.vm_ip)
        self.assertIsNone(self.test_virtualmachine.primary_ip6)

    def test_sync_complete_sets_primary_ip6(self):
        """sync_complete assigns primary_ip6 when present in _primary_ips."""
        global_ns = Namespace.objects.get(name="Global")
        Prefix.objects.get_or_create(
            network="2001:db8::",
            prefix_length=32,
            namespace=global_ns,
            status=self.status,
            type="network",
        )
        ipv6, _ = IPAddress.objects.get_or_create(host="2001:db8::1", mask_length=128, status=self.status)
        ipv6.vm_interfaces.set([self.vm_interface_1])

        adapter = self._make_adapter()
        adapter._primary_ips = [
            {
                "device": {"name": "Test VM"},
                "primary_ip4": None,
                "primary_ip6": "2001:db8::1",
            }
        ]

        adapter.sync_complete(source=MagicMock(), diff=MagicMock())

        self.test_virtualmachine.refresh_from_db()
        self.assertIsNone(self.test_virtualmachine.primary_ip4)
        self.assertEqual(self.test_virtualmachine.primary_ip6, ipv6)

    def test_sync_complete_sets_both_primary_ips(self):
        """sync_complete assigns both primary_ip4 and primary_ip6 when both are present."""
        global_ns = Namespace.objects.get(name="Global")
        Prefix.objects.get_or_create(
            network="2001:db8::",
            prefix_length=32,
            namespace=global_ns,
            status=self.status,
            type="network",
        )
        ipv6, _ = IPAddress.objects.get_or_create(host="2001:db8::1", mask_length=128, status=self.status)
        ipv6.vm_interfaces.set([self.vm_interface_1])

        adapter = self._make_adapter()
        adapter._primary_ips = [
            {
                "device": {"name": "Test VM"},
                "primary_ip4": "192.168.1.1",
                "primary_ip6": "2001:db8::1",
            }
        ]

        adapter.sync_complete(source=MagicMock(), diff=MagicMock())

        self.test_virtualmachine.refresh_from_db()
        self.assertEqual(self.test_virtualmachine.primary_ip4, self.vm_ip)
        self.assertEqual(self.test_virtualmachine.primary_ip6, ipv6)

    def test_sync_complete_vm_not_found_logs_warning(self):
        """sync_complete logs a warning and skips when VirtualMachine does not exist."""
        adapter = self._make_adapter()
        missing_device = {"name": "Nonexistent VM"}
        adapter._primary_ips = [
            {
                "device": missing_device,
                "primary_ip4": "192.168.1.1",
                "primary_ip6": None,
            }
        ]

        adapter.sync_complete(source=MagicMock(), diff=MagicMock())

        adapter.job.logger.warning.assert_called_once_with(
            f"VirtualMachine not found for {missing_device}, skipping primary IP assignment."
        )

    def test_sync_complete_ipaddress_not_found_logs_warning(self):
        """sync_complete logs a warning and skips when the primary IP does not exist in Nautobot."""
        adapter = self._make_adapter()
        adapter._primary_ips = [
            {
                "device": {"name": "Test VM", "cluster__name": "Test Cluster"},
                "primary_ip4": "203.0.113.1",
                "primary_ip6": None,
            }
        ]

        adapter.sync_complete(source=MagicMock(), diff=MagicMock())

        self.test_virtualmachine.refresh_from_db()
        self.assertIsNone(self.test_virtualmachine.primary_ip4)
        warning_calls = [
            call_args
            for call_args in adapter.job.logger.warning.call_args_list
            if "IPAddress 203.0.113.1 not found" in call_args.args[0]
        ]
        self.assertEqual(len(warning_calls), 1)

    def test_sync_complete_empty_primary_ips(self):
        """sync_complete does nothing and logs no warnings when _primary_ips is empty."""
        adapter = self._make_adapter()
        adapter._primary_ips = []

        adapter.sync_complete(source=MagicMock(), diff=MagicMock())

        adapter.job.logger.warning.assert_not_called()
        adapter.job.logger.error.assert_not_called()
