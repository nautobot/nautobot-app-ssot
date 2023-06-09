"""Test IPFabric Jobs."""
from copy import deepcopy

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from nautobot_ssot_ipfabric import jobs

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot_ipfabric", {})
BACKUP_CONFIG = deepcopy(CONFIG)


class IPFabricJobTest(TestCase):
    """Test the IPFabric job."""

    def test_metadata(self):
        """Verify correctness of the Job Meta attributes."""
        self.assertEqual("IPFabric ⟹ Nautobot", jobs.IpFabricDataSource.name)
        self.assertEqual("IPFabric ⟹ Nautobot", jobs.IpFabricDataSource.Meta.name)
        self.assertEqual("IP Fabric", jobs.IpFabricDataSource.Meta.data_source)
        self.assertEqual("Sync data from IP Fabric into Nautobot.", jobs.IpFabricDataSource.Meta.description)

    def test_data_mapping(self):
        """Verify correctness of the data_mappings() API."""
        mappings = jobs.IpFabricDataSource.data_mappings()

        self.assertEqual("Device", mappings[0].source_name)
        self.assertIsNone(mappings[0].source_url)
        self.assertEqual("Device", mappings[0].target_name)
        self.assertEqual(reverse("dcim:device_list"), mappings[0].target_url)

        self.assertEqual("Site", mappings[1].source_name)
        self.assertIsNone(mappings[1].source_url)
        self.assertEqual("Site", mappings[1].target_name)
        self.assertEqual(reverse("dcim:site_list"), mappings[1].target_url)

        self.assertEqual("Interfaces", mappings[2].source_name)
        self.assertIsNone(mappings[2].source_url)
        self.assertEqual("Interfaces", mappings[2].target_name)
        self.assertEqual(reverse("dcim:interface_list"), mappings[2].target_url)

        self.assertEqual("IP Addresses", mappings[3].source_name)
        self.assertIsNone(mappings[3].source_url)
        self.assertEqual("IP Addresses", mappings[3].target_name)
        self.assertEqual(reverse("ipam:ipaddress_list"), mappings[3].target_url)

        self.assertEqual("VLANs", mappings[4].source_name)
        self.assertIsNone(mappings[4].source_url)
        self.assertEqual("VLANs", mappings[4].target_name)
        self.assertEqual(reverse("ipam:vlan_list"), mappings[4].target_url)

    # @override_settings(
    #     PLUGINS_CONFIG={
    #         "nautobot_ssot_ipfabric": {
    #             "IPFABRIC_HOST": "https://ipfabric.networktocode.com",
    #             "IPFABRIC_API_TOKEN": "1234",
    #         }
    #     }
    # )
    # def test_config_information(self):
    #     """Verify the config_information() API."""
    #     CONFIG["ipfabric_host"] = "https://ipfabric.networktocode.com"
    #     config_information = jobs.IpFabricDataSource.config_information()
    #     self.assertContains(
    #         config_information,
    #         {
    #             "IP Fabric host": "https://ipfabric.networktocode.com",
    #         },
    #     )
    #     # CLEANUP
    #     CONFIG["ipfabric_host"] = BACKUP_CONFIG["ipfabric_host"]
