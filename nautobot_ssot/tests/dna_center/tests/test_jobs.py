"""Test DNA Center Jobs."""

from django.test import TestCase
from django.urls import reverse

from nautobot_ssot_dna_center import jobs


class DnaCenterDataSourceJobTest(TestCase):
    """Test the DNA Center DataSource Job."""

    def test_metadata(self):
        """Verify correctness of the Job Meta attributes."""
        self.assertEqual("DNA Center to Nautobot", jobs.DnaCenterDataSource.name)
        self.assertEqual("DNA Center to Nautobot", jobs.DnaCenterDataSource.Meta.name)
        self.assertEqual("DNA Center", jobs.DnaCenterDataSource.data_source)
        self.assertEqual("Sync information from DNA Center to Nautobot", jobs.DnaCenterDataSource.description)

    def test_data_mapping(self):
        mappings = jobs.DnaCenterDataSource.data_mappings()

        self.assertEqual("Areas", mappings[0].source_name)
        self.assertIsNone(mappings[0].source_url)
        self.assertEqual("Locations", mappings[0].target_name)
        self.assertEqual(reverse("dcim:location_list"), mappings[0].target_url)

        self.assertEqual("Buildings", mappings[1].source_name)
        self.assertIsNone(mappings[1].source_url)
        self.assertEqual("Locations", mappings[1].target_name)
        self.assertEqual(reverse("dcim:location_list"), mappings[1].target_url)

        self.assertEqual("Floors", mappings[2].source_name)
        self.assertIsNone(mappings[2].source_url)
        self.assertEqual("Locations", mappings[2].target_name)
        self.assertEqual(reverse("dcim:location_list"), mappings[2].target_url)

        self.assertEqual("Devices", mappings[3].source_name)
        self.assertIsNone(mappings[3].source_url)
        self.assertEqual("Devices", mappings[3].target_name)
        self.assertEqual(reverse("dcim:device_list"), mappings[3].target_url)

        self.assertEqual("Interfaces", mappings[4].source_name)
        self.assertIsNone(mappings[4].source_url)
        self.assertEqual("Interfaces", mappings[4].target_name)
        self.assertEqual(reverse("dcim:interface_list"), mappings[4].target_url)

        self.assertEqual("IP Addresses", mappings[5].source_name)
        self.assertIsNone(mappings[5].source_url)
        self.assertEqual("IP Addresses", mappings[5].target_name)
        self.assertEqual(reverse("ipam:ipaddress_list"), mappings[5].target_url)

    def test_config_information(self):
        """Verify the config_information() API."""
        config_information = jobs.DnaCenterDataSource.config_information()
        self.assertEqual(config_information, {"Instances": "Found in Extensibility -> External Integrations menu."})
