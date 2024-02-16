"""Test vSphere Jobs."""

from copy import deepcopy

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from nautobot_ssot.integrations.vsphere import jobs

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})
BACKUP_CONFIG = deepcopy(CONFIG)


class VsphereJobTest(TestCase):
    """Test the vSphere job."""

    def test_metadata(self):
        """Verify correctness of the Job Meta attributes."""
        self.assertEqual("VMWare vSphere ⟹ Nautobot", jobs.VsphereDataSource.name)
        self.assertEqual("VMWare vSphere ⟹ Nautobot", jobs.VsphereDataSource.Meta.name)
        self.assertEqual("VMWare vSphere", jobs.VsphereDataSource.Meta.data_source)
        self.assertEqual(
            "Sync data from VMWare vSphere into Nautobot.",
            jobs.VsphereDataSource.Meta.description,
        )

    def test_data_mapping(self):
        """Verify correctness of the data_mappings() API."""
        mappings = jobs.VsphereDataSource.data_mappings()

        self.assertEqual("Data Center", mappings[0].source_name)
        self.assertIsNone(mappings[0].source_url)
        self.assertEqual("ClusterGroup", mappings[0].target_name)
        self.assertEqual(reverse("virtualization:clustergroup_list"), mappings[0].target_url)

        self.assertEqual("Cluster", mappings[1].source_name)
        self.assertIsNone(mappings[1].source_url)
        self.assertEqual("Cluster", mappings[1].target_name)
        self.assertEqual(reverse("virtualization:cluster_list"), mappings[1].target_url)

        self.assertEqual("Virtual Machine", mappings[2].source_name)
        self.assertIsNone(mappings[2].source_url)
        self.assertEqual("Virtual Machine", mappings[2].target_name)
        self.assertEqual(reverse("virtualization:virtualmachine_list"), mappings[2].target_url)

        self.assertEqual("VM Interface", mappings[3].source_name)
        self.assertIsNone(mappings[3].source_url)
        self.assertEqual("VMInterface", mappings[3].target_name)
        self.assertEqual(reverse("virtualization:vminterface_list"), mappings[3].target_url)

        self.assertEqual("IP Addresses", mappings[4].source_name)
        self.assertIsNone(mappings[4].source_url)
        self.assertEqual("IP Addresses", mappings[4].target_name)
        self.assertEqual(reverse("ipam:ipaddress_list"), mappings[4].target_url)
