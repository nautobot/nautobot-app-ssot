"""Unit tests for the vSphere Diffsync adapter class."""

import os
import unittest

from nautobot_ssot.integrations.vsphere import defaults
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
                cluster_filter=None,
            )

    def test_load_clustergroups(self):
        mock_response = unittest.mock.MagicMock()
        mock_response.json.return_value = json_fixture(f"{FIXTURES}/get_datacenters.json")
        self.vsphere_adapter.client.get_datacenters.return_value = mock_response
        self.vsphere_adapter.load_cluster_groups()
        clustergroup = self.vsphere_adapter.get("clustergroup", "CrunchyDatacenter")
        self.assertEqual(clustergroup.name, "CrunchyDatacenter")

    def test_load_clusters(self):
        mock_response_clustergroup = unittest.mock.MagicMock()
        mock_response_clustergroup.return_value = json_fixture(f"{FIXTURES}/get_datacenters.json")["value"]
        self.vsphere_adapter.load_cluster_groups = mock_response_clustergroup
        self.vsphere_adapter.get_or_instantiate(self.vsphere_adapter.clustergroup, {"name": "CrunchyDatacenter"})

        mock_response_clusters = unittest.mock.MagicMock()
        mock_response_clusters.json.return_value = json_fixture(f"{FIXTURES}/get_clusters.json")
        self.vsphere_adapter.client.get_clusters_from_dc.return_value = mock_response_clusters
        self.vsphere_adapter.load_data()

        cluster = self.vsphere_adapter.get("cluster", "HeshLawCluster")
        self.assertEqual(cluster.name, "HeshLawCluster")
        self.assertEqual(cluster.cluster_type__name, "VMWare vSphere")
        self.assertEqual(cluster.cluster_group__name, "CrunchyDatacenter")

    def test_load_virtualmachines(self):
        mock_response_cluster = unittest.mock.MagicMock()
        mock_response_cluster.json.return_value = json_fixture(f"{FIXTURES}/get_vms_from_cluster.json")
        self.vsphere_adapter.client.get_vms_from_cluster.return_value = mock_response_cluster

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
        cluster, _ = self.vsphere_adapter.get_or_instantiate(
            self.vsphere_adapter.cluster,
            {"name": "HeshLawCluster"},
            {
                "cluster_type__name": defaults.DEFAULT_VSPHERE_TYPE,
                "cluster_group__name": "CrunchyDatacenter",
            },
        )
        diffsync_cluster = self.vsphere_adapter.get("cluster", "HeshLawCluster")

        self.vsphere_adapter.load_virtualmachines(cluster_json_info, diffsync_cluster)
        vm1 = self.vsphere_adapter.get("virtual_machine", "VMware vCenter Server")

        self.assertEqual(vm1.name, "VMware vCenter Server")
        self.assertEqual(vm1.vcpus, 6)
        self.assertEqual(vm1.memory, 32768)
        self.assertEqual(vm1.disk, 64)
        self.assertEqual(vm1.status__name, "Active")
        self.assertEqual(vm1.cluster__name, "HeshLawCluster")
        self.assertEqual(vm1.primary_ip4__host, "192.168.2.88")
        self.assertEqual(vm1.primary_ip6__host, None)

        vm2 = self.vsphere_adapter.get("virtual_machine", "Nautobot")
        self.assertEqual(vm2.name, "Nautobot")
        self.assertEqual(vm2.vcpus, 10)
        self.assertEqual(vm2.memory, 49152)
        self.assertEqual(vm2.disk, 64)
        self.assertEqual(vm2.status__name, "Active")
        self.assertEqual(vm2.cluster__name, "HeshLawCluster")
        self.assertIn("Nautobot", cluster.virtual_machines)
        # self.assertEqual(vm2.primary_ip4__host, "192.168.100.220")
        # self.assertEqual(vm2.primary_ip6__host, "fe80::250:56ff:feb5:ff89")

    def test_load_vm_interfaces(self):
        vm_detail_json = json_fixture(f"{FIXTURES}/vm_details_nautobot.json")["value"]
        diffsync_vm, _ = self.vsphere_adapter.get_or_instantiate(
            self.vsphere_adapter.virtual_machine,
            {"name": "Nautobot"},
            {
                "vcpus": 10,
                "memory": 49152,
                "disk": 64,
                "status__name": "Active",
                "cluster__name": "HeshLawCluster",
            },
        )

        self.vsphere_adapter.load_vm_interfaces(
            vsphere_virtual_machine=vm_detail_json,
            vm_id="vm-1015",
            diffsync_virtualmachine=diffsync_vm,
        )
        vm_interface = self.vsphere_adapter.get("interface", "Network adapter 1__Nautobot")
        self.assertEqual(vm_interface.name, "Network adapter 1")
        self.assertEqual(vm_interface.virtual_machine__name, "Nautobot")
        self.assertEqual(vm_interface.enabled, False)
        self.assertEqual(vm_interface.mac_address, "00:50:56:b5:e5:55")
        self.assertIn("Network adapter 1__Nautobot", diffsync_vm.interfaces)

    def test_load_ip_addresses(self):
        mock_interfaces = unittest.mock.MagicMock()
        mock_interfaces.json.return_value = json_fixture(f"{FIXTURES}/get_vm_interfaces.json")
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
            mock_interfaces.json()["value"], "00:50:56:b5:e5:5f", diffsync_vminterface
        )
        vm_ip = self.vsphere_adapter.get("ip_address", "192.168.2.88__23__Active")
        self.assertEqual(vm_ip.host, "192.168.2.88")
        self.assertEqual(vm_ip.mask_length, 23)
        self.assertEqual(vm_ip.status__name, "Active")
        self.assertEqual(vm_ip.vm_interfaces, [{"name": "Network adapter 1"}])

        prefix = self.vsphere_adapter.get("prefix", "192.168.2.0__23__Global__Active")
        self.assertEqual(prefix.network, "192.168.2.0")
        self.assertEqual(prefix.prefix_length, 23)
        self.assertEqual(prefix.namespace__name, "Global")
        self.assertEqual(prefix.type, "network")
