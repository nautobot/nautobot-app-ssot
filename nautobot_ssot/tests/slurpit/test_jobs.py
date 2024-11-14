"""Test IPFabric Jobs."""

from copy import deepcopy

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from nautobot_ssot.integrations.slurpit import jobs

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})
BACKUP_CONFIG = deepcopy(CONFIG)


class SlurpitJobTest(TestCase):
    """Test the Slurpit job."""

    def test_metadata(self):
        """Verify correctness of the Job Meta attributes."""
        self.assertEqual("Slurpit Data Source", jobs.SlurpitDataSource.name)
        self.assertEqual("Slurpit Data Source", jobs.SlurpitDataSource.Meta.name)
        self.assertEqual("Slurpit", jobs.SlurpitDataSource.Meta.data_source)
        self.assertEqual("Sync information from Slurpit to Nautobot.", jobs.SlurpitDataSource.Meta.description)

    def test_data_mapping(self):
        """Verify correctness of the data_mappings() API."""
        mappings = jobs.SlurpitDataSource.data_mappings()

        self.assertEqual("Site", mappings[0].source_name)
        self.assertIsNone(mappings[0].source_url)
        self.assertEqual("Location", mappings[0].target_name)
        self.assertEqual(reverse("dcim:location_list"), mappings[0].target_url)

        self.assertEqual("Manufacturer", mappings[1].source_name)
        self.assertIsNone(mappings[1].source_url)
        self.assertEqual("Manufacturer", mappings[1].target_name)
        self.assertEqual(reverse("dcim:manufacturer_list"), mappings[1].target_url)

        self.assertEqual("Device Type", mappings[2].source_name)
        self.assertIsNone(mappings[2].source_url)
        self.assertEqual("Device Type", mappings[2].target_name)
        self.assertEqual(reverse("dcim:devicetype_list"), mappings[2].target_url)

        self.assertEqual("Platform", mappings[3].source_name)
        self.assertIsNone(mappings[3].source_url)
        self.assertEqual("Platform", mappings[3].target_name)
        self.assertEqual(reverse("dcim:platform_list"), mappings[3].target_url)

        self.assertEqual("Role", mappings[4].source_name)
        self.assertIsNone(mappings[4].source_url)
        self.assertEqual("Role", mappings[4].target_name)
        self.assertEqual(reverse("extras:role_list"), mappings[4].target_url)

        self.assertEqual("Device", mappings[5].source_name)
        self.assertIsNone(mappings[5].source_url)
        self.assertEqual("Device", mappings[5].target_name)
        self.assertEqual(reverse("dcim:device_list"), mappings[5].target_url)

        self.assertEqual("Interface", mappings[6].source_name)
        self.assertIsNone(mappings[6].source_url)
        self.assertEqual("Interface", mappings[6].target_name)
        self.assertEqual(reverse("dcim:interface_list"), mappings[6].target_url)

        self.assertEqual("IP Address", mappings[7].source_name)
        self.assertIsNone(mappings[7].source_url)
        self.assertEqual("IP Address", mappings[7].target_name)
        self.assertEqual(reverse("ipam:ipaddress_list"), mappings[7].target_url)

        self.assertEqual("Prefix", mappings[8].source_name)
        self.assertIsNone(mappings[8].source_url)
        self.assertEqual("Prefix", mappings[8].target_name)
        self.assertEqual(reverse("ipam:prefix_list"), mappings[8].target_url)

        self.assertEqual("VLAN", mappings[9].source_name)
        self.assertIsNone(mappings[9].source_url)
        self.assertEqual("VLAN", mappings[9].target_name)
        self.assertEqual(reverse("ipam:vlan_list"), mappings[9].target_url)

        self.assertEqual("VRF", mappings[10].source_name)
        self.assertIsNone(mappings[10].source_url)
        self.assertEqual("VRF", mappings[10].target_name)
        self.assertEqual(reverse("ipam:vrf_list"), mappings[10].target_url)
