"""Test Proxmox VE Jobs."""

from django.urls import reverse
from nautobot.apps.testing import TestCase

from nautobot_ssot.integrations.proxmox import jobs


class ProxmoxJobTest(TestCase):
    """Test the Proxmox VE job."""

    def test_metadata(self):
        """Verify correctness of the Job Meta attributes."""
        self.assertEqual("Proxmox VE ⟹ Nautobot", jobs.ProxmoxDataSource.name)
        self.assertEqual("Proxmox VE ⟹ Nautobot", jobs.ProxmoxDataSource.Meta.name)
        self.assertEqual("Proxmox VE", jobs.ProxmoxDataSource.Meta.data_source)
        self.assertEqual(
            "Sync data from Proxmox VE into Nautobot.",
            jobs.ProxmoxDataSource.Meta.description,
        )

    def test_data_mappings(self):
        """Verify correctness of the data_mappings() API."""
        mappings = jobs.ProxmoxDataSource.data_mappings()

        expected = [
            ("Cluster", "ClusterGroup", reverse("virtualization:clustergroup_list")),
            ("Cluster", "Cluster", reverse("virtualization:cluster_list")),
            ("Node", "Device", reverse("dcim:device_list")),
            ("Node Interface", "Interface", reverse("dcim:interface_list")),
            ("Virtual Machine", "Virtual Machine", reverse("virtualization:virtualmachine_list")),
            ("VM Interface", "VMInterface", reverse("virtualization:vminterface_list")),
            ("IP Addresses", "IP Addresses", reverse("ipam:ipaddress_list")),
        ]
        self.assertEqual(len(mappings), len(expected))
        for mapping, (source_name, target_name, target_url) in zip(mappings, expected):
            self.assertEqual(mapping.source_name, source_name)
            self.assertIsNone(mapping.source_url)
            self.assertEqual(mapping.target_name, target_name)
            self.assertEqual(mapping.target_url, target_url)
