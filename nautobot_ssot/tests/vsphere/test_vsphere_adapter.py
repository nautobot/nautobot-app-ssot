"""Unit tests for the vSphere Diffsync adapter class."""

import os
import unittest
from unittest.mock import Mock

from nautobot_ssot.integrations.vsphere.diffsync.adapters.adapter_vsphere import (
    VsphereDiffSync,
)

from .vsphere_fixtures import create_default_vsphere_config, json_fixture, real_path

FIXTURES = os.environ.get("FIXTURE_DIR", real_path)


class TestVsphereAdapter(unittest.TestCase):
    """Test cases for vSphereAdapter."""

    def setUp(self):
        self.config = create_default_vsphere_config()
        with unittest.mock.patch(
            "nautobot_ssot.integrations.vsphere.utilities.vsphere_client.VsphereClient",
            autospec=True,
        ) as mock_client:
            self.vsphere_adapter = VsphereDiffSync(
                job=unittest.mock.Mock(),
                sync=unittest.mock.Mock(),
                client=mock_client,
                config=self.config,
                cluster_filters=None,
            )

    def resp_with_json(self, path):
        """Generator for mock responses with JSON data."""
        r = Mock()
        r.json.return_value = json_fixture(path)
        return r

    def test_load_clustergroups(self):
        self.vsphere_adapter.client.get_datacenters.return_value = self.resp_with_json(
            f"{FIXTURES}/get_datacenters.json"
        )
        self.vsphere_adapter.load_cluster_groups()
        clustergroup = self.vsphere_adapter.get("clustergroup", "CrunchyDatacenter")
        self.assertEqual(clustergroup.name, "CrunchyDatacenter")

    def test_load_clusters(self):
        mock_response_clustergroup = unittest.mock.MagicMock()
        mock_response_clustergroup.return_value = json_fixture(f"{FIXTURES}/get_datacenters.json")["value"]
        self.vsphere_adapter.load_cluster_groups = mock_response_clustergroup
        self.vsphere_adapter.get_or_instantiate(self.vsphere_adapter.clustergroup, {"name": "CrunchyDatacenter"})

        self.vsphere_adapter.client.get_clusters_from_dc.return_value = self.resp_with_json(
            f"{FIXTURES}/get_clusters.json"
        )
        self.vsphere_adapter.load_data()

        cluster = self.vsphere_adapter.get("cluster", "HeshLawCluster")
        self.assertEqual(cluster.name, "HeshLawCluster")
        self.assertEqual(cluster.cluster_type__name, "VMWare vSphere")
        self.assertEqual(cluster.cluster_group__name, "CrunchyDatacenter")

    def test_load_virtualmachines(self):
        self.vsphere_adapter.client.get_vms_from_cluster.return_value = self.resp_with_json(
            f"{FIXTURES}/get_vms_from_cluster.json"
        )

        mock_response_vm_details = unittest.mock.MagicMock()
        mock_response_vm_details.json.side_effect = [
            json_fixture(f"{FIXTURES}/vm_details_vsphere.json"),
            json_fixture(f"{FIXTURES}/vm_details_nautobot.json"),
        ]
        self.vsphere_adapter.client.get_vm_details.return_value = mock_response_vm_details

        mock_response_get_vm_interfaces = unittest.mock.MagicMock()
        mock_response_get_vm_interfaces.json.side_effect = [
            json_fixture(f"{FIXTURES}/get_vm_interfaces.json"),
            json_fixture(f"{FIXTURES}/get_vm_interfaces_1.json"),
        ]

        self.vsphere_adapter.client.get_vm_interfaces.return_value = mock_response_get_vm_interfaces

        cluster_json_info = json_fixture(f"{FIXTURES}/get_clusters.json")["value"][0]
        diffsync_cluster = self.vsphere_adapter.get_or_instantiate(
            self.vsphere_adapter.cluster,
            {"name": "HeshLawCluster", "cluster_type__name": "VMWare vSphere"},
        )

        self.vsphere_adapter.tag_map = {
            "urn:vmomi:InventoryServiceTag:cb703991-b580-4751-ae2d-22c70a426311:GLOBAL": {
                "name": "Owner__EEE",
                "associations": [{"type": "VirtualMachine", "id": "vm-1012"}],
            }
        }

        self.vsphere_adapter.load_virtualmachines(cluster_json_info, diffsync_cluster)
        vm1 = self.vsphere_adapter.get(
            "virtual_machine",
            {"name": "VMware vCenter Server", "cluster__name": "HeshLawCluster"},
        )

        self.assertEqual(vm1.name, "VMware vCenter Server")
        self.assertEqual(vm1.vcpus, 6)
        self.assertEqual(vm1.memory, 32768)
        self.assertEqual(vm1.disk, 64)
        self.assertEqual(vm1.status__name, "Active")
        self.assertEqual(vm1.cluster__name, "HeshLawCluster")
        self.assertEqual(vm1.primary_ip4__host, "192.168.2.88")
        self.assertEqual(vm1.primary_ip6__host, None)
        self.assertEqual(len(vm1.tags), 2)
        self.assertIn("Owner__EEE", [tag["name"] for tag in vm1.tags])

        vm2 = self.vsphere_adapter.get("virtual_machine", {"name": "Nautobot", "cluster__name": "HeshLawCluster"})
        self.assertEqual(vm2.name, "Nautobot")
        self.assertEqual(vm2.vcpus, 10)
        self.assertEqual(vm2.memory, 49152)
        self.assertEqual(vm2.disk, 64)
        self.assertEqual(vm2.status__name, "Active")
        self.assertEqual(vm2.cluster__name, "HeshLawCluster")
        self.assertEqual(vm2.primary_ip4__host, "172.18.0.1")
        self.assertEqual(len(vm2.tags), 1)
        self.assertIn("SSoT Synced from vSphere", [tag["name"] for tag in vm2.tags])

    def test_load_vm_interfaces(self):
        vm_detail_json = json_fixture(f"{FIXTURES}/vm_details_nautobot.json")["value"]
        diffsync_vm, _ = self.vsphere_adapter.get_or_instantiate(
            self.vsphere_adapter.virtual_machine,
            {"name": "Nautobot", "cluster__name": "HeshLawCluster"},
            {
                "vcpus": 10,
                "memory": 49152,
                "disk": 64,
                "status__name": "Active",
            },
        )

        self.vsphere_adapter.load_vm_interfaces(
            vsphere_virtual_machine_details=vm_detail_json,
            vm_id="vm-1015",
            diffsync_virtualmachine=diffsync_vm,
        )
        vm_interface = self.vsphere_adapter.get("interface", "Network adapter 1__Nautobot")
        self.assertEqual(vm_interface.name, "Network adapter 1")
        self.assertEqual(vm_interface.virtual_machine__name, "Nautobot")
        self.assertEqual(vm_interface.enabled, False)
        self.assertEqual(vm_interface.mac_address, "00:50:56:B5:E5:55")
        self.assertIn("Network adapter 1__Nautobot", diffsync_vm.interfaces)

    def test_load_ip_addresses(self):
        mock_interfaces = unittest.mock.MagicMock()
        mock_interfaces.json.return_value = json_fixture(f"{FIXTURES}/get_vm_interfaces.json")
        diffsync_virtualmachine, _ = self.vsphere_adapter.get_or_instantiate(
            self.vsphere_adapter.virtual_machine,
            {"name": "Nautobot", "cluster__name": "HeshLawCluster"},
            {
                "vcpus": 10,
                "memory": 49152,
                "disk": 64,
                "status__name": "Active",
            },
        )
        diffsync_vminterface, _ = self.vsphere_adapter.get_or_instantiate(
            self.vsphere_adapter.interface,
            {"name": "Network adapter 1", "virtual_machine__name": "Nautobot"},
            {
                "enabled": False,
                "mac_address": "00:50:56:b5:e5:5f",
                "status__name": "Active",
            },
        )

        self.vsphere_adapter.load_ip_addresses(
            mock_interfaces.json()["value"],
            "00:50:56:b5:e5:5f",
            diffsync_vminterface,
            diffsync_virtualmachine,
        )
        self.vsphere_adapter.load_ip_map()

        vm_ip = self.vsphere_adapter.get(
            "ip_address",
            "192.168.2.88__23__Active",
        )
        self.assertEqual(vm_ip.host, "192.168.2.88")
        self.assertEqual(vm_ip.mask_length, 23)
        self.assertEqual(vm_ip.status__name, "Active")
        self.assertEqual(
            vm_ip.vm_interfaces,
            [{"name": "Network adapter 1", "virtual_machine__name": "Nautobot"}],
        )

        prefix = self.vsphere_adapter.get(
            "prefix",
            "192.168.2.0__23__Global__Active",
        )
        self.assertEqual(prefix.network, "192.168.2.0")
        self.assertEqual(prefix.prefix_length, 23)
        self.assertEqual(prefix.namespace__name, "Global")
        self.assertEqual(prefix.type, "network")

    def test_load_ipv6_addresses(self):
        mock_interfaces = unittest.mock.MagicMock()
        mock_interfaces.json.return_value = json_fixture(f"{FIXTURES}/get_vm_interfaces_ipv6.json")
        diffsync_virtualmachine, _ = self.vsphere_adapter.get_or_instantiate(
            self.vsphere_adapter.virtual_machine,
            {"name": "Nautobot", "cluster__name": "HeshLawCluster"},
            {
                "vcpus": 10,
                "memory": 49152,
                "disk": 64,
                "status__name": "Active",
            },
        )
        diffsync_vminterface, _ = self.vsphere_adapter.get_or_instantiate(
            self.vsphere_adapter.interface,
            {"name": "Network adapter 1", "virtual_machine__name": "Nautobot"},
            {
                "enabled": False,
                "mac_address": "00:50:56:b5:e5:5f",
                "status__name": "Active",
            },
        )

        self.vsphere_adapter.load_ip_addresses(
            mock_interfaces.json()["value"],
            "00:50:56:b5:e5:5f",
            diffsync_vminterface,
            diffsync_virtualmachine,
        )

        # Must call load_ip_map to populate the IP since I'm deferring it.
        self.vsphere_adapter.load_ip_map()
        vm_ip = self.vsphere_adapter.get(
            "ip_address",
            "2001:0db8:85a3:0000:0000:8a2e:0370:7334__64__Active",
        )
        self.assertEqual(vm_ip.host, "2001:0db8:85a3:0000:0000:8a2e:0370:7334")
        self.assertEqual(vm_ip.mask_length, 64)
        self.assertEqual(vm_ip.status__name, "Active")
        self.assertEqual(
            vm_ip.vm_interfaces,
            [{"name": "Network adapter 1", "virtual_machine__name": "Nautobot"}],
        )

        prefix = self.vsphere_adapter.get("prefix", "2001:db8:85a3::__64__Global__Active")
        self.assertEqual(prefix.network, "2001:db8:85a3::")
        self.assertEqual(prefix.prefix_length, 64)
        self.assertEqual(prefix.namespace__name, "Global")
        self.assertEqual(prefix.type, "network")

    def test_load_tags(self):
        """Test loading tags from vSphere."""
        self.vsphere_adapter.client.get_tags.return_value = self.resp_with_json(f"{FIXTURES}/get_tags.json")
        self.vsphere_adapter.client.get_tag_associations.return_value = self.resp_with_json(
            f"{FIXTURES}/get_tag_associations.json"
        )
        self.vsphere_adapter.client.get_tag_details.return_value = self.resp_with_json(
            f"{FIXTURES}/get_tag_details.json"
        )
        self.vsphere_adapter.client.get_category_details.return_value = self.resp_with_json(
            f"{FIXTURES}/get_category_details.json"
        )

        self.vsphere_adapter.load_tags()
        tags = self.vsphere_adapter.get_all("tag")
        self.assertEqual(len(tags), 1)
        self.assertIn("Owner__EEE", [tag.name for tag in tags])
